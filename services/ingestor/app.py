#!/usr/bin/env python3
"""
文件匯入服務 (Ingestor Service)
支援本地目錄掃描、文件切分、向量索引與知識圖譜建立
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# === 環境變數 ===
GATEWAY_BASE = os.environ.get("GATEWAY_BASE", "http://apigw:8000").rstrip("/")
GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "dev-key")
APP_VERSION = os.environ.get("APP_VERSION", "v0.2.1")

# 切分參數
DEFAULT_CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))

# === FastAPI 應用 ===
app = FastAPI(title="FreeRoute RAG Ingestor", version=APP_VERSION)

# 日誌設定
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ingestor")


# === 請求/回應模型 ===
class IngestDirReq(BaseModel):
    path: str = Field(..., description="本地目錄路徑")
    collection: str = Field(default="chunks", description="Qdrant collection 名稱")
    file_patterns: List[str] = Field(default=["*.md", "*.txt", "*.html"], description="檔案模式")
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, description="切分大小")
    chunk_overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, description="切分重疊")
    extract_graph: bool = Field(default=True, description="是否抽取知識圖譜")
    force_reprocess: bool = Field(default=False, description="是否強制重新處理")


class IngestResp(BaseModel):
    ok: bool
    message: str
    stats: Dict[str, Any]
    processed_files: List[str]
    errors: List[Dict[str, str]]


class HealthResp(BaseModel):
    ok: bool
    gateway_status: str


# === 工具函式 ===
def _sha256(text: str) -> str:
    """計算文件內容 hash"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _simple_chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """簡單的文本切分"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # 嘗試在句號或換行處切分
        if end < len(text):
            last_period = chunk.rfind("。")
            last_newline = chunk.rfind("\n")
            cut_point = max(last_period, last_newline)
            if cut_point > start + chunk_size // 2:  # 確保切分點合理
                chunk = text[start : start + cut_point + 1]
                end = start + cut_point + 1

        chunks.append(chunk.strip())
        start = max(end - overlap, start + 1)  # 防止無限迴圈

    return [c for c in chunks if c.strip()]


def _call_gateway(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """呼叫 Gateway API"""
    url = urljoin(GATEWAY_BASE, endpoint)
    headers = {"X-API-Key": GATEWAY_API_KEY, "Content-Type": "application/json"}

    try:
        # 圖譜抽取需要更長時間，其他 API 用較短超時
        timeout = 120 if endpoint == "/graph/extract" else 30
        response = requests.post(url, json=data, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Gateway API error ({endpoint}): {e}")


def _load_file_content(file_path: Path) -> str:
    """載入文件內容"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # 嘗試其他編碼
        try:
            with open(file_path, "r", encoding="gbk") as f:
                return f.read()
        except Exception:
            with open(file_path, "r", encoding="latin-1") as f:
                return f.read()


# === API 路由 ===
@app.get("/health", response_model=HealthResp)
def health() -> Dict[str, Any]:
    """健康檢查"""
    gateway_status = "unknown"
    try:
        response = requests.get(f"{GATEWAY_BASE}/health", timeout=5)
        gateway_status = "ok" if response.status_code == 200 else f"error_{response.status_code}"
    except Exception as e:
        gateway_status = f"error_{str(e)[:50]}"

    return {"ok": True, "gateway_status": gateway_status}


@app.post("/ingest/directory", response_model=IngestResp)
def ingest_directory(req: IngestDirReq) -> Dict[str, Any]:
    """匯入本地目錄"""
    start_time = time.time()

    # 驗證目錄
    dir_path = Path(req.path)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {req.path}")

    # 收集文件
    all_files = []
    for pattern in req.file_patterns:
        all_files.extend(dir_path.rglob(pattern))

    if not all_files:
        return {
            "ok": True,
            "message": "No files found matching patterns",
            "stats": {"files_found": 0, "processing_time_sec": 0},
            "processed_files": [],
            "errors": [],
        }

    logger.info(f"Found {len(all_files)} files in {req.path}")

    # 處理狀態追蹤
    processed_files = []
    errors = []
    stats = {
        "files_found": len(all_files),
        "files_processed": 0,
        "chunks_created": 0,
        "graphs_extracted": 0,
        "skipped_unchanged": 0,
    }

    # 簡單的處理狀態儲存（實務中應用 Redis 或 DB）
    processed_hashes = set()  # 假設已處理的文件 hash 集合

    for file_path in all_files:
        try:
            # 載入文件
            content = _load_file_content(file_path)
            if not content.strip():
                continue

            content_hash = _sha256(content)
            doc_id = str(file_path.relative_to(dir_path))

            # 檢查是否需要重新處理
            if not req.force_reprocess and content_hash in processed_hashes:
                stats["skipped_unchanged"] += 1
                continue

            # 1. 切分文件
            chunks = _simple_chunk_text(content, chunk_size=req.chunk_size, overlap=req.chunk_overlap)

            if not chunks:
                continue

            # 2. 建立向量索引
            chunk_data = []
            for i, chunk_text in enumerate(chunks):
                chunk_data.append(
                    {
                        "doc_id": doc_id,
                        "text": chunk_text,
                        "metadata": {
                            "file_path": str(file_path),
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "content_hash": content_hash,
                        },
                    }
                )

            try:
                index_resp = _call_gateway("/index/chunks", {"collection": req.collection, "chunks": chunk_data})
                stats["chunks_created"] += index_resp.get("upserted", 0)
                logger.info(f"Indexed {len(chunk_data)} chunks for {doc_id}")
            except Exception as e:
                errors.append({"file": doc_id, "stage": "indexing", "error": str(e)})
                logger.error(f"Failed to index chunks for {doc_id}: {e}")
                continue

            # 3. 抽取知識圖譜（可選）
            if req.extract_graph:
                try:
                    # 對文件進行圖抽取，限制長度並分段處理
                    content_for_graph = content[:3000]  # 進一步限制長度
                    graph_resp = _call_gateway(
                        "/graph/extract",
                        {
                            "context": content_for_graph,
                            "strict": False,  # 改為非嚴格模式，容錯性更好
                            "allow_empty": True,  # 允許空結果
                            "max_attempts": 1,  # 減少重試次數
                        },
                    )

                    # 將抽取的圖譜儲存
                    if graph_resp.get("ok") and graph_resp.get("data"):
                        upsert_resp = _call_gateway("/graph/upsert", {"data": graph_resp["data"]})
                        stats["graphs_extracted"] += 1
                        logger.info(
                            f"Extracted graph for {doc_id}: {upsert_resp.get('nodes', 0)} nodes, {upsert_resp.get('edges', 0)} edges"
                        )

                except Exception as e:
                    errors.append({"file": doc_id, "stage": "graph_extraction", "error": str(e)})
                    logger.error(f"Failed to extract graph for {doc_id}: {e}")

            processed_files.append(doc_id)
            processed_hashes.add(content_hash)
            stats["files_processed"] += 1

        except Exception as e:
            errors.append({"file": str(file_path), "stage": "loading", "error": str(e)})
            logger.error(f"Failed to process {file_path}: {e}")

    processing_time = time.time() - start_time
    stats["processing_time_sec"] = round(processing_time, 2)

    return {
        "ok": True,
        "message": f"Processed {stats['files_processed']}/{stats['files_found']} files",
        "stats": stats,
        "processed_files": processed_files,
        "errors": errors,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
