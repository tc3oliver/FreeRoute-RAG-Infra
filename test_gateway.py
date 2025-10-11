#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import time
from typing import Any, Dict

import requests

# 可選：若有安裝 jsonschema 才做本地驗證
try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except Exception:
    HAS_JSONSCHEMA = False

DEFAULT_BASE = os.environ.get("API_GATEWAY_BASE", "http://localhost:8000")
DEFAULT_KEY = os.environ.get("API_GATEWAY_KEY", "dev-key")
DEFAULT_HEADER = os.environ.get("API_GATEWAY_AUTH_HEADER", "X-API-Key")  # or "Authorization"

# 與 Gateway/TokenCap 對齊的 Graph Schema
GRAPH_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "minLength": 1},
                    "props": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "key": {"type": "string", "minLength": 1},
                                "value": {"type": ["string", "number", "boolean", "null"]},
                            },
                            "required": ["key", "value"],
                        },
                        "minItems": 0,
                    },
                },
                "required": ["id", "type", "props"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "src": {"type": "string", "minLength": 1},
                    "dst": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "minLength": 1},
                    "props": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "key": {"type": "string", "minLength": 1},
                                "value": {"type": ["string", "number", "boolean", "null"]},
                            },
                            "required": ["key", "value"],
                        },
                        "minItems": 0,
                    },
                },
                "required": ["src", "dst", "type", "props"],
            },
        },
    },
    "required": ["nodes", "edges"],
}


def pretty(title: str, obj: Any) -> None:
    print(f"\n=== {title} ===")
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(str(obj))
    print("=" * 60)


def make_headers(key: str, auth_header: str) -> Dict[str, str]:
    if auth_header.lower() == "authorization":
        return {"Authorization": f"Bearer {key}"}
    return {"X-API-Key": key}


def ensure_ok(resp: requests.Response) -> Dict[str, Any]:
    text = resp.text
    try:
        data = resp.json()
    except Exception:
        data = {"_non_json": text, "_status": resp.status_code}
        if not resp.ok:
            # 不直接 raise，先把內容回傳讓呼叫者印出來
            return {"ok": False, "status": resp.status_code, "body": text}
        return data
    if not resp.ok:
        return {"ok": False, "status": resp.status_code, "body": data}
    return data


def do_health(base: str):
    r = requests.get(f"{base}/health", timeout=10)
    return ensure_ok(r)


def do_whoami(base: str, headers: Dict[str, str]):
    r = requests.get(f"{base}/whoami", headers=headers, timeout=10)
    return ensure_ok(r)


def do_chat(base: str, headers: Dict[str, str]):
    payload = {
        "model": "rag-answer",
        "messages": [{"role": "user", "content": "請用三點條列這個系統的用途"}],
        "json_mode": True,
        "temperature": 0.2,
    }
    r = requests.post(f"{base}/chat", headers=headers, json=payload, timeout=120)
    return ensure_ok(r)


def do_embed(base: str, headers: Dict[str, str]):
    payload = {"texts": ["這是第一段測試文字", "這是第二段測試文字"]}
    r = requests.post(f"{base}/embed", headers=headers, json=payload, timeout=60)
    # vectors 太長 不要印出來
    print("raw response:", r.text[:200] + ("..." if len(r.text) > 200 else ""))

    return r.text[:200]


def do_rerank(base: str, headers: Dict[str, str]):
    payload = {
        "query": "什麼是 LiteLLM？",
        "documents": [
            "LiteLLM 是一個代理層，提供 OpenAI 相容 API，支援多供應商與路由。",
            "這是一個與主題無關的段落。",
            "LiteLLM 也能做 fallback、費用控額與熔斷冷卻。",
        ],
        "top_n": 2,
    }
    r = requests.post(f"{base}/rerank", headers=headers, json=payload, timeout=60)
    return ensure_ok(r)


def do_graph(
    base: str,
    headers: Dict[str, str],
    context: str = None,
    strict: bool = True,
    repair: bool = True,
):
    if not context:
        context = "Nick 於 2022 年加入 Acme 擔任工程師；Acme 總部位於台北，創辦人是 Bob。"
    payload = {"context": context, "strict": strict, "repair_if_invalid": repair}
    r = requests.post(f"{base}/graph/extract", headers=headers, json=payload, timeout=180)
    print("raw response:", r.text)
    data = ensure_ok(r)

    # 本地驗證（若安裝 jsonschema）
    if HAS_JSONSCHEMA and strict:
        try:
            validate(instance=data.get("data", {}), schema=GRAPH_JSON_SCHEMA)
            data["_schema_validated_locally"] = True
        except Exception as e:
            data["_schema_validated_locally"] = False
            data["_schema_error"] = str(e)
    else:
        data["_schema_validated_locally"] = False
    return data


def run_all(base: str, headers: Dict[str, str], skip_graph: bool):
    pretty("HEALTH", do_health(base))
    time.sleep(0.1)
    pretty("WHOAMI", do_whoami(base, headers))
    time.sleep(0.1)
    pretty("CHAT", do_chat(base, headers))
    time.sleep(0.1)
    pretty("EMBED", do_embed(base, headers))
    time.sleep(0.1)
    pretty("RERANK", do_rerank(base, headers))
    if not skip_graph:
        time.sleep(0.1)
        pretty("GRAPH EXTRACT", do_graph(base, headers))


def main():
    ap = argparse.ArgumentParser(description="FreeRoute RAG Infra – API Gateway tester (no /usage)")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"API base (default: {DEFAULT_BASE})")
    ap.add_argument(
        "--key", default=DEFAULT_KEY, help="API key (default from env API_GATEWAY_KEY or 'dev-key')"
    )
    ap.add_argument(
        "--auth-header",
        default=DEFAULT_HEADER,
        choices=["X-API-Key", "Authorization"],
        help=f"Auth header to use (default: {DEFAULT_HEADER})",
    )
    ap.add_argument("--skip-graph", action="store_true", help="Skip /graph/extract test")
    ap.add_argument(
        "--only",
        choices=["health", "whoami", "chat", "embed", "rerank", "graph"],
        help="Run only a specific test",
    )
    args = ap.parse_args()

    base = args.base.rstrip("/")
    headers = make_headers(args.key, args.auth_header)

    if args.only:
        if args.only == "health":
            pretty("HEALTH", do_health(base))
            return
        if args.only == "whoami":
            pretty("WHOAMI", do_whoami(base, headers))
            return
        if args.only == "chat":
            pretty("CHAT", do_chat(base, headers))
            return
        if args.only == "embed":
            pretty("EMBED", do_embed(base, headers))
            return
        if args.only == "rerank":
            pretty("RERANK", do_rerank(base, headers))
            return
        if args.only == "graph":
            if args.skip_graph:
                print("skip_graph is set; nothing to run.")
                return
            pretty("GRAPH EXTRACT", do_graph(base, headers))
            return

    run_all(base, headers, args.skip_graph)


if __name__ == "__main__":
    main()
