#!/usr/bin/env python3
import argparse
import json
import os
import sys
import traceback
from typing import Tuple

from openai import OpenAI

LITELLM_BASE = os.getenv("LITELLM_BASE", "http://localhost:9400/v1")
LITELLM_KEY = os.getenv("LITELLM_KEY", "sk-admin")

CHAT_MODELS = [
    "rag-answer",  # openai/gpt-5-mini-2025-08-07
    "rag-answer-gemini",  # gemini/gemini-2.5-flash（你的命名）
    "rag-answer-openrouter",  # openrouter/mistral-3.2-24b-instruct（你的命名）
    "rag-answer-groq",  # groq/llama-3.1-8b-instant
]
GRAPH_MODELS = [
    "graph-extractor",  # gpt-4.1-mini
    "graph-extractor-o1mini",  # o1-mini
    "graph-extractor-gemini",  # gemini-2.5-flash（你的命名）
]
EMBED_MODEL = "local-embed"  # ollama/bge-m3 (embedding)


def client():
    return OpenAI(base_url=LITELLM_BASE, api_key=LITELLM_KEY)


def ok_txt(model: str, provider_model: str, content: str) -> Tuple[bool, str]:
    if isinstance(content, str) and content.strip():
        sample = content.strip().replace("\n", " ")[:80]
        return True, f"OK - {model} → {provider_model} | sample: {sample!r}"
    return False, f"FAIL(empty) - {model} → {provider_model}"


def test_chat(model: str) -> Tuple[bool, str]:
    try:
        c = client()
        resp = c.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "這是一個模型連通性測試。"}],
            temperature=0.2,
            timeout=60,
        )
        content = resp.choices[0].message.content
        return ok_txt(model, resp.model, content)
    except Exception as e:
        return False, f"FAIL - {model} | {e}"


def test_graph(model: str, strict_json: bool = False) -> Tuple[bool, str]:
    try:
        c = client()
        msgs = [
            {
                "role": "system",
                "content": "你是資訊抽取引擎，只輸出 JSON（若無法則輸出簡短文字）。",
            },
            {"role": "user", "content": "Bob 於2022年加入 Acme 擔任工程師；Acme 總部位於台北。"},
        ]
        extra = {}
        if strict_json:
            # OpenAI 支援；其他供應商會被 drop_params 忽略
            extra["response_format"] = {"type": "json_object"}
        resp = c.chat.completions.create(
            model=model, messages=msgs, temperature=0.0, timeout=60, **extra
        )
        txt = resp.choices[0].message.content
        if strict_json:
            try:
                data = json.loads(txt)
                # 只要是 dict 就當成功；可選再檢查 nodes/edges
                if isinstance(data, dict):
                    return True, f"OK(JSON) - {model} → {resp.model} | keys={list(data)[:3]}"
                return False, f"FAIL(JSON-type) - {model} → {resp.model}"
            except Exception as je:
                return False, f"FAIL(JSON-parse) - {model} → {resp.model} | {je}"
        else:
            return ok_txt(model, resp.model, txt)
    except Exception as e:
        return False, f"FAIL - {model} | {e}"


def test_embed(model: str) -> Tuple[bool, str]:
    try:
        c = client()
        resp = c.embeddings.create(
            model=model, input=["這是第一段測試嵌入", "這是第二段測試嵌入"], timeout=60
        )
        vecs = [d.embedding for d in resp.data]
        if vecs and isinstance(vecs[0], list) and len(vecs[0]) > 0:
            return True, f"OK - {model} | count={len(vecs)} dim={len(vecs[0])}"
        return False, f"FAIL(empty-vec) - {model}"
    except Exception as e:
        return False, f"FAIL - {model} | {e}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-json", action="store_true", help="Graph 模型強制 JSON 驗證")
    args = parser.parse_args()

    print(f"== Using LITELLM_BASE={LITELLM_BASE}  LITELLM_KEY={LITELLM_KEY[:4]}*** ==")
    all_ok = True

    print("\n[Chat Models]")
    for m in CHAT_MODELS:
        s, msg = test_chat(m)
        all_ok &= s
        print(msg)

    print("\n[Graph Extractor Models]")
    for m in GRAPH_MODELS:
        s, msg = test_graph(m, strict_json=args.strict_json)
        all_ok &= s
        print(msg)

    print("\n[Embeddings]")
    s, msg = test_embed(EMBED_MODEL)
    all_ok &= s
    print(msg)

    print("\n== RESULT:", "ALL PASS ✅" if all_ok else "SOME FAILED ❌")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
