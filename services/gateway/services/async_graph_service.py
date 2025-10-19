"""
Async graph extraction and management service.

This module provides asynchronous versions of graph operations with significant
performance improvements through:
- Parallel provider attempts (instead of serial fallback)
- Non-blocking LLM and database operations
- Concurrent graph extraction and repair
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from jsonschema import validate
from openai import AsyncOpenAI

from ..config import (
    GRAPH_ALLOW_EMPTY,
    GRAPH_JSON_SCHEMA,
    GRAPH_MAX_ATTEMPTS,
    GRAPH_MIN_EDGES,
    GRAPH_MIN_NODES,
    GRAPH_SCHEMA_HASH,
    PROVIDER_CHAIN,
)
from ..middleware import log_event
from ..models import KV, GraphData, GraphProbeReq, GraphQueryReq, GraphReq, GraphUpsertReq
from ..repositories import get_async_litellm_client, get_async_neo4j_driver
from ..utils import extract_json_obj, normalize_graph_shape, prune_graph, retry_once_429_async

logger = logging.getLogger("gateway")


class AsyncGraphService:
    """
    Service for graph extraction, storage, and querying (asynchronous).

    This is the preferred service for all new code.
    Provides significant performance improvements through:
    - Parallel provider attempts (try multiple providers simultaneously)
    - Non-blocking LLM API calls
    - Async database operations
    """

    def __init__(self):
        self.client: AsyncOpenAI | None = None
        self.neo4j_driver: Any = None

    async def _ensure_llm(self) -> None:
        """Ensure LLM client is initialized (async-only)."""
        if self.client is None:
            self.client = await get_async_litellm_client()

    async def _ensure_neo4j(self) -> None:
        """Ensure Neo4j driver is initialized (async-only)."""
        if self.neo4j_driver is None:
            self.neo4j_driver = await get_async_neo4j_driver()

    async def probe(self, req: GraphProbeReq, client_ip: str) -> Dict[str, Any]:
        """
        Test a provider's JSON/text generation capability (asynchronous).

        Args:
            req: Probe request with model and settings
            client_ip: Client IP for tracking

        Returns:
            Dict with 'ok', 'mode', 'data/text', 'provider' keys
        """
        await self._ensure_llm()

        messages = req.messages or [
            {"role": "system", "content": "你是資訊抽取引擎，只輸出 JSON（若無法則輸出簡短文字）。"},
            {"role": "user", "content": "Bob 於2022年加入 Acme 擔任工程師；Acme 總部位於台北。"},
        ]

        if req.strict_json:
            has_json_word = any(
                isinstance(m, dict) and isinstance(m.get("content"), str) and ("json" in m["content"].lower())
                for m in messages
            )
            if not has_json_word:
                messages = [{"role": "system", "content": "請以 JSON 物件回覆（JSON only）。"}] + messages

        extra = {}
        if req.strict_json:
            extra["response_format"] = {"type": "json_object"}

        async def _call():
            return await self.client.chat.completions.create(
                model=req.model,
                messages=messages,
                temperature=req.temperature,
                timeout=req.timeout,
                extra_headers={"X-Client-IP": client_ip},
                **extra,
            )

        resp = await retry_once_429_async(_call)
        txt = resp.choices[0].message.content or ""
        provider = resp.model

        if req.strict_json:
            try:
                data = json.loads(txt)
                if isinstance(data, dict):
                    return {"ok": True, "mode": "json", "data": data, "provider": provider}
                return {
                    "ok": False,
                    "mode": "json",
                    "error": "JSON not an object",
                    "provider": provider,
                    "raw": txt,
                }
            except Exception as je:
                return {
                    "ok": False,
                    "mode": "json",
                    "error": f"json_parse_error: {je}",
                    "provider": provider,
                    "raw": txt,
                }
        else:
            return {"ok": True, "mode": "text", "text": txt, "provider": provider}

    async def extract(self, req: GraphReq, client_ip: str) -> Dict[str, Any]:
        """
        Extract graph data from text using parallel provider attempts (asynchronous).

        Key improvement: Instead of trying providers one by one (serial), we try
        multiple providers in parallel and return the first successful result.
        This significantly reduces latency for graph extraction.

        Args:
            req: Graph extraction request
            client_ip: Client IP for tracking

        Returns:
            Dict with 'ok', 'data', 'provider', 'schema_hash' keys

        Raises:
            HTTPException: If extraction fails after all attempts
        """
        min_nodes = int(req.min_nodes) if req.min_nodes is not None else GRAPH_MIN_NODES
        min_edges = int(req.min_edges) if req.min_edges is not None else GRAPH_MIN_EDGES
        allow_empty = bool(req.allow_empty) if req.allow_empty is not None else GRAPH_ALLOW_EMPTY
        max_attempts = int(req.max_attempts) if req.max_attempts is not None else GRAPH_MAX_ATTEMPTS
        provider_chain = req.provider_chain if req.provider_chain else PROVIDER_CHAIN

        if not req.context or not isinstance(req.context, str) or not req.context.strip():
            raise ValueError("context must be a non-empty string")

        await self._ensure_llm()

        SYS_BASE = (
            "你是資訊抽取引擎，將中文文本轉為圖譜資料（nodes/edges）。"
            "規則：僅根據【context】抽取，不得捏造；每個節點/關係需附 props（key/value 列表）。"
            "若資訊不足，可輸出低置信候選，並以 {'key':'low_confidence','value':true} 標記。"
            "必須輸出至少一條關係（例如『就職於/創立/位於』等）。"
            "只輸出 JSON，並嚴格符合系統 Schema。"
        )
        USER_TMPL = (
            "【context】\n{ctx}\n\n"
            "【任務】抽取 nodes/edges，並盡量補充 props（日期/金額/地點/職稱/URL 等）。\n"
            "建議關係類型示例：\n"
            "- EMPLOYED_AT: props 包含 role（職稱）、start_date（起始時間）、location（地點）\n"
            "- FOUNDED_BY: props 可含 year（年份）\n"
            "- HEADQUARTERED_IN: props 可含 city（城市）\n"
            "禁止輸出非 JSON、禁止空白字串、禁止 Markdown。"
        )

        # Strategy: Try providers in parallel (first 2-3), then fallback to sequential
        parallel_count = min(3, len(provider_chain))

        # Try first batch in parallel
        for batch_start in range(0, len(provider_chain), parallel_count):
            batch_providers = provider_chain[batch_start : batch_start + parallel_count]

            # Create parallel tasks for this batch
            tasks = []
            for provider in batch_providers:
                task = self._try_provider_with_attempts(
                    provider, req, max_attempts, min_nodes, min_edges, allow_empty, SYS_BASE, USER_TMPL
                )
                tasks.append(task)

            # Wait for first successful result or all failures
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check results in order of completion
            for i, result in enumerate(results):
                provider = batch_providers[i]
                if isinstance(result, dict) and result.get("ok"):
                    log_event(
                        "extraction succeeded",
                        event="graph.extract.success",
                        provider=provider,
                        parallel_batch=batch_start // parallel_count,
                    )
                    return result
                elif isinstance(result, Exception):
                    log_event(
                        "provider batch failed",
                        event="graph.extract.provider_failed",
                        provider=provider,
                        error=str(result),
                        level=logging.WARNING,
                    )

        # If we reach here, all providers failed
        log_event(
            "all providers exhausted",
            event="graph.extract.exhausted",
            provider_count=len(provider_chain),
            level=logging.ERROR,
        )

        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={
                "error": "graph_extraction_failed",
                "message": "no provider produced acceptable output",
                "min_nodes": min_nodes,
                "min_edges": min_edges,
                "allow_empty": allow_empty,
                "max_attempts": max_attempts,
                "provider_chain": provider_chain,
                "schema_hash": GRAPH_SCHEMA_HASH,
            },
        )

    async def _try_provider_with_attempts(
        self,
        provider: str,
        req: GraphReq,
        max_attempts: int,
        min_nodes: int,
        min_edges: int,
        allow_empty: bool,
        sys_base: str,
        user_tmpl: str,
    ) -> Dict[str, Any]:
        """Try a single provider with multiple attempts."""
        for attempt in range(1, max_attempts + 1):
            mode = "strict" if attempt == 1 else "nudge"
            try:
                result = await self._call_once(provider, req, mode, sys_base, user_tmpl)
                data = result["data"]

                log_event(
                    "attempt finished",
                    event="graph.extract.attempt",
                    attempt=attempt,
                    provider=provider,
                    mode=mode,
                    nodes=len(data.get("nodes", [])),
                    edges=len(data.get("edges", [])),
                )

                if self._is_single_error_node(data):
                    log_event(
                        "single error node produced",
                        event="graph.extract.error_node",
                        attempt=attempt,
                        provider=provider,
                        mode=mode,
                        level=logging.WARNING,
                    )
                    continue

                nodes = data.get("nodes", []) if isinstance(data, dict) else []
                edges = data.get("edges", []) if isinstance(data, dict) else []

                if allow_empty or (len(nodes) >= min_nodes and len(edges) >= min_edges):
                    return {
                        "ok": True,
                        "data": data,
                        "provider": result["provider"],
                        "schema_hash": GRAPH_SCHEMA_HASH,
                    }

            except Exception as e:
                log_event(
                    "attempt failed",
                    event="graph.extract.failed",
                    attempt=attempt,
                    provider=provider,
                    mode=mode,
                    error=str(e),
                    level=logging.WARNING,
                )

                # Try repair if enabled
                if req.repair_if_invalid:
                    try:
                        repaired = await self._repair_invalid_output(provider, str(e), req.strict)
                        if repaired and not self._is_single_error_node(repaired):
                            n2 = len(repaired.get("nodes", [])) if isinstance(repaired, dict) else 0
                            e2 = len(repaired.get("edges", [])) if isinstance(repaired, dict) else 0
                            if allow_empty or (n2 >= min_nodes and e2 >= min_edges):
                                return {
                                    "ok": True,
                                    "data": repaired,
                                    "provider": provider,
                                    "schema_hash": GRAPH_SCHEMA_HASH,
                                }
                    except Exception:
                        pass  # Continue to next attempt

        # All attempts failed for this provider
        raise Exception(f"Provider {provider} exhausted after {max_attempts} attempts")

    async def _call_once(
        self, entrypoint: str, req: GraphReq, mode: str, sys_base: str, user_tmpl: str
    ) -> Dict[str, Any]:
        """Make a single extraction call."""
        sys_prompt = sys_base
        if mode == "strict":
            sys_prompt += " 回覆不得回傳完全空陣列。"
        elif mode == "nudge":
            sys_prompt += " 若資訊不足，請輸出低置信候選並以 low_confidence=true 標記。"

        user_msg = user_tmpl.format(ctx=req.context)
        rf = {"type": "json_object"}
        if entrypoint == "graph-extractor-gemini":
            rf = None

        resp = await self.client.chat.completions.create(
            model=entrypoint,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            **({"response_format": rf} if rf else {}),
        )

        raw = resp.choices[0].message.content or ""
        try:
            obj = json.loads(raw)
        except Exception:
            obj = extract_json_obj(raw)

        data = normalize_graph_shape(obj)

        if req.strict:
            data = prune_graph(data)
            validate(instance=data, schema=GRAPH_JSON_SCHEMA)

        if os.environ.get("DEBUG_GRAPH", "false").lower() == "true":
            print(
                f"[GraphExtract] normalized data: nodes={len(data.get('nodes', []))}, "
                f"edges={len(data.get('edges', []))}"
            )

        return {"data": data, "provider": resp.model, "raw": raw}

    async def upsert(self, req: GraphUpsertReq) -> Dict[str, Any]:
        """
        Upsert graph nodes and edges into Neo4j (asynchronous).

        Args:
            req: Upsert request with graph data

        Returns:
            Dict with 'ok', 'nodes', and 'edges' counts
        """
        await self._ensure_neo4j()
        data = req.data

        def _props_json(props: List[KV]) -> str:
            return json.dumps([{"key": p.key, "value": p.value} for p in (props or [])], ensure_ascii=False)

        n_count = 0
        e_count = 0

        async with self.neo4j_driver.session() as session:
            # Upsert nodes
            for n in data.nodes:
                await session.run(
                    """
                    MERGE (x:Entity:`%s` {id: $id})
                    ON CREATE SET x.created_at = timestamp()
                    SET x.updated_at = timestamp(), x.type = $type, x.props_json = $props
                    """
                    % n.type,
                    id=n.id,
                    type=n.type,
                    props=_props_json(n.props),
                )
                n_count += 1

            # Upsert edges
            for e in data.edges:
                await session.run(
                    """
                    MATCH (a {id: $src})
                    MATCH (b {id: $dst})
                    MERGE (a)-[r:`%s`]->(b)
                    ON CREATE SET r.created_at = timestamp()
                    SET r.updated_at = timestamp(), r.type = $type, r.props_json = $props
                    """
                    % e.type,
                    src=e.src,
                    dst=e.dst,
                    type=e.type,
                    props=_props_json(e.props),
                )
                e_count += 1

        return {"ok": True, "nodes": n_count, "edges": e_count}

    async def query(self, req: GraphQueryReq) -> Dict[str, Any]:
        """
        Execute a read-only Cypher query on Neo4j (asynchronous).

        Args:
            req: Query request with Cypher and params

        Returns:
            Dict with 'ok' and 'records' keys
        """
        q = (req.query or "").strip()
        if not q:
            raise ValueError("query is required")

        # Safety check: reject write operations
        lowered = q.lower()
        forbidden = ["delete ", "remove ", "drop ", "create ", "set ", "merge ", "load ", "call db."]
        if any(tok in lowered for tok in forbidden):
            raise ValueError("write_or_unsafe_query_not_allowed")

        await self._ensure_neo4j()

        records = []
        async with self.neo4j_driver.session() as session:
            result = await session.run(q, **(req.params or {}))
            records = [record.data() async for record in result]

        return {"ok": True, "records": records}

    async def _repair_invalid_output(self, provider: str, error_msg: str, strict: bool) -> Dict[str, Any] | None:
        """Attempt to repair invalid JSON output (asynchronous)."""
        FIX_SYS = "請把下列輸出修正成『合法 JSON』且符合 Schema；不得改動語意；只回傳 JSON 本體。"
        FIX_USER = f"【schema】\n{json.dumps(GRAPH_JSON_SCHEMA, ensure_ascii=False)}\n\n【llm_output】\n{error_msg}"

        resp = await self.client.chat.completions.create(
            model=provider,
            messages=[
                {"role": "system", "content": FIX_SYS},
                {"role": "user", "content": FIX_USER},
            ],
            temperature=0.0,
        )
        fixed = resp.choices[0].message.content or ""
        try:
            data = json.loads(fixed)
        except Exception:
            data = extract_json_obj(fixed)

        if strict:
            validate(instance=data, schema=GRAPH_JSON_SCHEMA)

        return data

    @staticmethod
    def _is_single_error_node(d: Dict[str, Any]) -> bool:
        """Check if graph contains only a single error node."""
        try:
            if not isinstance(d, dict):
                return False
            ns = d.get("nodes", [])
            es = d.get("edges", [])
            if isinstance(ns, list) and isinstance(es, list) and len(ns) == 1:
                n0 = ns[0]
                return isinstance(n0, dict) and n0.get("type") == "error"
            return False
        except Exception:
            return False
