#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This file is the moved smoke test. It runs end-to-end against a running service
# Keep behaviour unchanged from previous `tests/gateway/test_gateway.py` script.

import argparse
import json
import os
import time
from typing import Any, Dict

import requests

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except Exception:
    HAS_JSONSCHEMA = False

DEFAULT_BASE = os.environ.get("API_GATEWAY_BASE", "http://localhost:9800")
DEFAULT_KEY = os.environ.get("API_GATEWAY_KEY", "dev-key")
DEFAULT_HEADER = os.environ.get("API_GATEWAY_AUTH_HEADER", "X-API-Key")

# Graph schema omitted for brevity - smoke test uses same helpers as before


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
    return data


def run_all(base: str, headers: Dict[str, str], skip_graph: bool):
    print("HEALTH", do_health(base))
    time.sleep(0.1)
    print("WHOAMI", do_whoami(base, headers))
    time.sleep(0.1)
    print("CHAT", do_chat(base, headers))
    time.sleep(0.1)
    print("EMBED", do_embed(base, headers))
    time.sleep(0.1)
    print("RERANK", do_rerank(base, headers))
    if not skip_graph:
        time.sleep(0.1)
        print("GRAPH EXTRACT", do_graph(base, headers))


def main():
    ap = argparse.ArgumentParser(description="FreeRoute RAG Infra – API Gateway smoke tester")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--auth-header", default=DEFAULT_HEADER)
    ap.add_argument("--skip-graph", action="store_true")
    args = ap.parse_args()

    headers = make_headers(args.key, args.auth_header)
    run_all(args.base, headers, args.skip_graph)


if __name__ == "__main__":
    main()
