import logging
import os
from typing import Any, Dict, List

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
    device = "cuda" if torch.cuda.is_available() else "cpu"
else:
    device = DEVICE_ENV

dtype_map = {
    "bf16": torch.bfloat16,
    "bfloat16": torch.bfloat16,
    "fp16": torch.float16,
    "float16": torch.float16,
    "fp32": torch.float32,
    "float32": torch.float32,
}
dtype = dtype_map.get(DTYPE_ENV, torch.bfloat16 if device == "cuda" else torch.float32)

tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
model = (
    AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID, trust_remote_code=True, torch_dtype=dtype
    )
    .to(device)
    .eval()
)


class RerankReq(BaseModel):
    query: str = Field(..., description="search/query text")
    documents: List[str] = Field(..., description="candidate documents")
    top_n: int = Field(6, ge=1, description="top-N results to return")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "device": device, "dtype": str(dtype), "model": MODEL_ID}


@app.post("/rerank")
def rerank(req: RerankReq) -> Dict[str, Any]:
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
        ).to(device)

        with torch.no_grad():
            logits = model(**enc).logits.squeeze(-1)
            scores = logits.detach().float().tolist()
    except Exception as e:
        logger.exception("rerank inference error")
        raise HTTPException(status_code=500, detail=f"inference_error: {e}")

    ranked = sorted(list(enumerate(scores)), key=lambda x: x[1], reverse=True)[: req.top_n]
    return {
        "ok": True,
        "results": [{"index": i, "score": float(s), "text": docs[i]} for i, s in ranked],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
