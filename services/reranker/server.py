import logging
import os
from typing import Any, Dict, List

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

app = FastAPI(title="PyTorch Reranker (bge-reranker-v2-m3)", version="1.0")
logger = logging.getLogger("reranker")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

MODEL_ID = os.environ.get("MODEL_ID", "BAAI/bge-reranker-v2-m3")
DEVICE_ENV = os.environ.get("DEVICE", "auto")
DTYPE_ENV = os.environ.get("DTYPE", "bfloat16").lower()
TOKEN_MAXLEN = int(os.environ.get("TOKEN_MAXLEN", "512"))

if DEVICE_ENV == "auto":
    _device_str = "cuda" if torch.cuda.is_available() else "cpu"
else:
    _device_str = DEVICE_ENV

# use torch.device for consistent .to() behaviour and device comparisons
device = torch.device(_device_str)
# Track model device globally for consistent moves
MODEL_DEVICE = device

dtype_map = {
    "bf16": torch.bfloat16,
    "bfloat16": torch.bfloat16,
    "fp16": torch.float16,
    "float16": torch.float16,
    "fp32": torch.float32,
    "float32": torch.float32,
}
dtype = dtype_map.get(DTYPE_ENV, torch.bfloat16 if device.type == "cuda" else torch.float32)

try:
    logger.info(
        "[Reranker] loading tokenizer/model model=%s device=%s dtype=%s", MODEL_ID, device, dtype
    )
    tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = (
        AutoModelForSequenceClassification.from_pretrained(
            MODEL_ID, trust_remote_code=True, torch_dtype=dtype
        )
        .to(device)
        .eval()
    )
    # capture the exact device the model is on (e.g., cuda:0)
    try:
        MODEL_DEVICE = next(model.parameters()).device
    except Exception:
        MODEL_DEVICE = device
    cuda_available = torch.cuda.is_available()
    cuda_devices = torch.cuda.device_count() if cuda_available else 0
    cuda_name = torch.cuda.get_device_name(0) if cuda_available and cuda_devices > 0 else ""
    logger.info(
        "[Reranker] ready model=%s device=%s dtype=%s torch=%s cuda=%s devices=%s name=%s",
        MODEL_ID,
        device,
        dtype,
        torch.__version__,
        cuda_available,
        cuda_devices,
        cuda_name,
    )
except Exception as e:
    logger.exception("[Reranker] failed to load model %s: %s", MODEL_ID, e)
    raise


class RerankReq(BaseModel):
    query: str = Field(..., description="search/query text")
    documents: List[str] = Field(..., description="candidate documents")
    top_n: int = Field(6, ge=1, description="top-N results to return")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "device": str(device), "dtype": str(dtype), "model": MODEL_ID}


class RerankItem(BaseModel):
    index: int
    score: float
    text: str


class RerankResp(BaseModel):
    ok: bool
    results: List[RerankItem]


@app.post("/rerank", response_model=RerankResp, tags=["rerank"])
def rerank(req: RerankReq) -> RerankResp:
    if not req.query or not isinstance(req.query, str):
        raise HTTPException(status_code=400, detail="query must be a non-empty string")
    if not isinstance(req.documents, list) or not req.documents:
        raise HTTPException(
            status_code=400, detail="documents must be a non-empty array of strings"
        )

    docs = [d for d in req.documents if isinstance(d, str) and d.strip()]
    if not docs:
        raise HTTPException(status_code=400, detail="no valid documents provided")

    pairs = [(req.query, d) for d in docs]
    try:
        enc = tok.batch_encode_plus(
            pairs, padding=True, truncation=True, max_length=TOKEN_MAXLEN, return_tensors="pt"
        )
        # Move BatchEncoding directly if supported; this is the most reliable path
        target_dev = MODEL_DEVICE
        try:
            if hasattr(enc, "to"):
                enc = enc.to(target_dev)
        except Exception:
            pass

        # Fallback: ensure dict and move items
        if not isinstance(enc, dict):
            try:
                enc = dict(enc)
            except Exception:
                enc = enc
        if isinstance(enc, dict):
            for k, v in list(enc.items()):
                if torch.is_tensor(v):
                    enc[k] = v.to(target_dev, non_blocking=True)
            # Ensure id-like tensors are int64 on device
            for id_key in ("input_ids", "token_type_ids", "position_ids"):
                if id_key in enc and torch.is_tensor(enc[id_key]):
                    enc[id_key] = enc[id_key].to(target_dev).long()

        # debug: log devices/dtypes/shapes of encoded inputs to trace device mismatches
        try:
            items_iter = (
                enc.items()
                if isinstance(enc, dict)
                else (enc.items() if hasattr(enc, "items") else [])
            )
            for k, v in items_iter:
                if torch.is_tensor(v):
                    logger.info(
                        "[Reranker] enc key=%s device=%s dtype=%s shape=%s",
                        k,
                        v.device,
                        v.dtype,
                        tuple(v.shape),
                    )
                else:
                    logger.info("[Reranker] enc key=%s type=%s", k, type(v).__name__)
        except Exception:
            logger.info("[Reranker] failed to introspect enc for debugging")

        # Build strict inputs dict using only model-relevant keys and ensure correct device/dtype
        strict_inputs: Dict[str, torch.Tensor] = {}
        for k in ("input_ids", "attention_mask", "token_type_ids", "position_ids"):
            if isinstance(enc, dict) and k in enc and torch.is_tensor(enc[k]):
                t = enc[k].to(MODEL_DEVICE, non_blocking=True)
                # ensure indices are long dtype (except attention_mask which can remain as-is)
                if k != "attention_mask" and t.dtype != torch.long:
                    t = t.long()
                strict_inputs[k] = t

        # final guard log
        for k, v in strict_inputs.items():
            logger.info(
                "[Reranker] strict key=%s device=%s dtype=%s shape=%s",
                k,
                v.device,
                v.dtype,
                tuple(v.shape),
            )

        with torch.no_grad():
            logits = model(**strict_inputs).logits.squeeze(-1)
            scores = logits.detach().float().tolist()
    except RuntimeError as e:
        # CUDA OOM、device mismatch 或其他 runtime error
        exc_text = str(e)
        hint = ""
        if "CUDA out of memory" in exc_text:
            hint = "reduce top_n or TOKEN_MAXLEN, or switch DTYPE/DEVICE or use a smaller model"
        elif "Expected all tensors to be on the same device" in exc_text:
            hint = "device mismatch: please check that all tensors are moved to the same device (cpu/cuda). This is now auto-handled, but if you see this, please report."
        # try to include current cuda reserved memory if available
        mem_info = {}
        try:
            if torch.cuda.is_available():
                mem_info = {
                    "reserved": torch.cuda.memory_reserved(0),
                    "allocated": torch.cuda.memory_allocated(0),
                    "max_allocated": torch.cuda.max_memory_allocated(0),
                }
        except Exception:
            mem_info = {}

        logger.exception(
            "[Reranker] inference runtime error model=%s device=%s dtype=%s error=%s hint=%s mem=%s",
            MODEL_ID,
            device,
            dtype,
            exc_text,
            hint,
            mem_info,
        )
        raise HTTPException(
            status_code=500, detail={"error": "inference_error", "message": exc_text, "hint": hint}
        )
    except Exception as e:
        logger.exception("[Reranker] inference error model=%s error=%s", MODEL_ID, e)
        raise HTTPException(status_code=500, detail={"error": "inference_error", "message": str(e)})

    ranked = sorted(list(enumerate(scores)), key=lambda x: x[1], reverse=True)[: req.top_n]
    return {
        "ok": True,
        "results": [{"index": i, "score": float(s), "text": docs[i]} for i, s in ranked],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
