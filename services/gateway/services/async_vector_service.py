"""
Async vector indexing and retrieval service.

This module provides asynchronous versions of vector operations with significant
performance improvements through:
- Parallel vector search and graph expansion
- Batch embedding generation
- Non-blocking database operations
"""

import asyncio
import time
import uuid as uuidlib
from typing import Any, Dict, List

from openai import AsyncOpenAI

from ..models import Citation, IndexChunksReq, RetrieveHit, RetrieveReq, SearchReq, Subgraph, SubgraphEdge, SubgraphNode
from ..repositories import (
    ensure_qdrant_collection_async,
    get_async_litellm_client,
    get_async_neo4j_driver,
    get_async_qdrant_client,
)
from ..utils import sha1


class AsyncVectorService:
    async def delete_vector(self, collection: str, tenant_id: str = "default") -> dict:
        """Delete a vector collection for a tenant."""
        await self._ensure_clients()
        collection_name = f"{collection}_{tenant_id}"
        await self.qdrant_client.delete_collection(collection_name)
        return {"ok": True, "collection": collection_name}

    """
    Service for vector indexing, search, and hybrid retrieval (asynchronous).

    This is the preferred service for all new code.
    Provides significant performance improvements through:
    - Parallel vector search + graph expansion in retrieve()
    - Batch embedding generation
    - Non-blocking I/O operations
    """

    def __init__(self):
        self.llm_client: AsyncOpenAI | None = None
        self.qdrant_client: Any = None
        self.neo4j_driver: Any = None

    async def _ensure_clients(self) -> None:
        """Lazy initialization of all clients (async-only)."""
        if self.llm_client is None:
            self.llm_client = await get_async_litellm_client()
        if self.qdrant_client is None:
            self.qdrant_client = await get_async_qdrant_client()
        if self.neo4j_driver is None:
            self.neo4j_driver = await get_async_neo4j_driver()

    async def index_chunks(self, req: IndexChunksReq, tenant_id: str = "default") -> Dict[str, Any]:
        """
        Index text chunks into Qdrant vector database (asynchronous).

        Supports tenant isolation: chunks are indexed into tenant-specific collection.

        Args:
            req: Index request with chunks and collection name
            tenant_id: Tenant identifier for isolation (default: "default")

        Returns:
            Dict with 'ok', 'upserted', 'dim', and 'collection' keys
        """
        if not req.chunks:
            raise ValueError("chunks must be non-empty")

        await self._ensure_clients()

        # 1) Generate embeddings
        texts = [c.text for c in req.chunks]
        emb = await self.llm_client.embeddings.create(model="local-embed", input=texts)
        vectors = [d.embedding for d in emb.data]
        dim = len(vectors[0]) if vectors else 0

        # 2) Upsert to Qdrant (tenant-aware collection)
        actual_collection = await ensure_qdrant_collection_async(
            self.qdrant_client, req.collection, dim, tenant_id=tenant_id
        )

        import importlib

        models_mod = importlib.import_module("qdrant_client.models")
        PointStruct = getattr(models_mod, "PointStruct")

        points = []
        for c, vec in zip(req.chunks, vectors):
            # Validate or generate UUID
            pid = None
            if c.chunk_id:
                try:
                    pid = str(uuidlib.UUID(str(c.chunk_id)))
                except Exception:
                    pid = None
            if not pid:
                pid = str(uuidlib.uuid4())

            payload = {
                "doc_id": c.doc_id,
                "text": c.text,
                "metadata": c.metadata or {},
                "hash": sha1(c.text),
                "tenant_id": tenant_id,  # Add tenant_id to payload for filtering
            }
            points.append(PointStruct(id=pid, vector=vec, payload=payload))

        await self.qdrant_client.upsert(collection_name=actual_collection, points=points)
        return {
            "ok": True,
            "upserted": len(points),
            "dim": dim,
            "collection": actual_collection,
            "tenant_id": tenant_id,
        }

    async def search(self, req: SearchReq, tenant_id: str = "default") -> Dict[str, Any]:
        """
        Vector similarity search (asynchronous).

        Supports tenant isolation: searches only in tenant-specific collection.

        Args:
            req: Search request with query and filters
            tenant_id: Tenant identifier for isolation (default: "default")

        Returns:
            Dict with 'ok' and 'hits' keys
        """
        # Validate query
        if not req.query or not req.query.strip():
            raise ValueError("query must be non-empty")

        await self._ensure_clients()

        # Generate query embedding
        emb = await self.llm_client.embeddings.create(model="local-embed", input=[req.query])
        qvec = emb.data[0].embedding

        # Search Qdrant (tenant-aware collection)
        import importlib

        models_mod = importlib.import_module("qdrant_client.models")
        Filter = getattr(models_mod, "Filter")

        # Import get_tenant_collection_name
        from ..repositories import get_tenant_collection_name

        actual_collection = get_tenant_collection_name(tenant_id, req.collection)

        flt = None
        if req.filters:
            flt = Filter.from_dict(req.filters)

        results = await self.qdrant_client.search(
            collection_name=actual_collection, query_vector=qvec, limit=req.top_k, query_filter=flt
        )

        hits = []
        for r in results:
            hits.append({"id": getattr(r, "id", None), "score": r.score, "payload": r.payload or {}})

        return {"ok": True, "hits": hits}

    async def retrieve(self, req: RetrieveReq, tenant_id: str = "default") -> Dict[str, Any]:
        """
        Hybrid retrieval: vector search + graph neighborhood expansion (asynchronous).

        This method provides significant performance improvement by running
        vector search and graph expansion in parallel using asyncio.gather().

        Supports tenant isolation: searches only in tenant-specific data.

        Args:
            req: Retrieve request with query and options
            tenant_id: Tenant identifier for isolation (default: "default")

        Returns:
            Dict with 'ok', 'hits', 'subgraph', and 'query_time_ms' keys
        """
        # Validate query
        if not req.query or not req.query.strip():
            raise ValueError("query must be non-empty")

        start_time = time.time()
        await self._ensure_clients()

        # Execute vector search and graph expansion in parallel
        tasks = []

        # Task 1: Vector search
        tasks.append(self._vector_search(req, tenant_id))

        # Task 2: Graph expansion (if requested)
        if req.include_subgraph:
            tasks.append(self._expand_graph_neighborhood(req.query, req.max_hops, tenant_id))
        else:
            tasks.append(asyncio.sleep(0))  # Dummy task to maintain index

        # Wait for both tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process vector search results
        vector_hits = []
        if not isinstance(results[0], Exception):
            vector_hits = results[0]

        # Process graph expansion results
        subgraph_data = None
        if req.include_subgraph and not isinstance(results[1], Exception):
            subgraph_data = results[1]

        query_time = int((time.time() - start_time) * 1000)

        return {
            "ok": True,
            "hits": vector_hits,
            "subgraph": subgraph_data.model_dump() if subgraph_data else None,
            "query_time_ms": query_time,
        }

    async def _vector_search(self, req: RetrieveReq, tenant_id: str = "default") -> List[RetrieveHit]:
        """Execute vector search and return hits."""
        try:
            emb = await self.llm_client.embeddings.create(model="local-embed", input=[req.query])
            qvec = emb.data[0].embedding

            import importlib

            from ..repositories import get_tenant_collection_name

            actual_collection = get_tenant_collection_name(tenant_id, req.collection)

            models_mod = importlib.import_module("qdrant_client.models")
            Filter = getattr(models_mod, "Filter")

            flt = None
            if req.filters:
                flt = Filter.from_dict(req.filters)

            results = await self.qdrant_client.search(
                collection_name=actual_collection, query_vector=qvec, limit=req.top_k, query_filter=flt
            )

            hits = []
            for r in results:
                payload = r.payload or {}
                citation = Citation(source="vector", doc_id=payload.get("doc_id"), score=r.score)
                hit = RetrieveHit(
                    text=payload.get("text", ""),
                    metadata=payload.get("metadata", {}),
                    citations=[citation],
                    score=r.score,
                )
                hits.append(hit)

            return hits
        except Exception:
            return []  # Return empty list on error

    async def _expand_graph_neighborhood(
        self, query: str, max_hops: int, tenant_id: str = "default"
    ) -> Subgraph | None:
        """Expand graph neighborhood based on query keywords (asynchronous with tenant isolation)."""
        try:
            query_keywords = [kw.strip() for kw in query.lower().split() if len(kw.strip()) > 2]

            async with self.neo4j_driver.session() as session:
                # Find relevant nodes (tenant-aware)
                match_nodes = []
                for keyword in query_keywords[:3]:
                    result = await session.run(
                        """
                        MATCH (n {tenant_id: $tenant_id})
                        WHERE toLower(n.id) CONTAINS $keyword
                           OR ANY(prop IN keys(n) WHERE toLower(toString(n[prop])) CONTAINS $keyword)
                        RETURN DISTINCT n.id as id, n.type as type, properties(n) as props
                        LIMIT 5
                    """,
                        keyword=keyword,
                        tenant_id=tenant_id,
                    )
                    records = [record async for record in result]
                    match_nodes.extend([r.data() for r in records])

                # Deduplicate nodes
                seen_ids = set()
                unique_nodes = []
                for node in match_nodes:
                    if node["id"] not in seen_ids:
                        unique_nodes.append(node)
                        seen_ids.add(node["id"])

                # Expand neighborhood
                all_nodes = []
                all_edges = []

                for node in unique_nodes[:3]:
                    node_id = node["id"]
                    result = await session.run(
                        f"""
                        MATCH (a {{id: $id, tenant_id: $tenant_id}})-[r]-(b {{tenant_id: $tenant_id}})
                        RETURN
                            a.id as src_id, a.type as src_type, properties(a) as src_props,
                            type(r) as rel_type, properties(r) as rel_props,
                            b.id as dst_id, b.type as dst_type, properties(b) as dst_props,
                            startNode(r).id = $id as is_outgoing
                        LIMIT {max_hops * 10}
                    """,
                        id=node_id,
                        tenant_id=tenant_id,
                    )

                    records = [record async for record in result]
                    for record in records:
                        data = record.data()
                        src_node = SubgraphNode(
                            id=data["src_id"], type=data["src_type"] or "Entity", props=data["src_props"] or {}
                        )
                        dst_node = SubgraphNode(
                            id=data["dst_id"], type=data["dst_type"] or "Entity", props=data["dst_props"] or {}
                        )

                        if src_node not in all_nodes:
                            all_nodes.append(src_node)
                        if dst_node not in all_nodes:
                            all_nodes.append(dst_node)

                        if data["is_outgoing"]:
                            edge = SubgraphEdge(
                                src=data["src_id"],
                                dst=data["dst_id"],
                                type=data["rel_type"],
                                props=data["rel_props"] or {},
                            )
                        else:
                            edge = SubgraphEdge(
                                src=data["dst_id"],
                                dst=data["src_id"],
                                type=data["rel_type"],
                                props=data["rel_props"] or {},
                            )

                        if edge not in all_edges:
                            all_edges.append(edge)

                if all_nodes:
                    return Subgraph(nodes=all_nodes, edges=all_edges)
        except Exception:
            pass  # Return None if graph expansion fails

        return None

    async def delete(self, req, tenant_id: str = "default") -> int:
        """
        刪除向量資料（支援多租戶、collection、doc_id 粒度）
        """
        await self._ensure_clients()
        from ..repositories import get_tenant_collection_name

        collection = get_tenant_collection_name(tenant_id, req.collection)
        if req.doc_id:
            # 刪除指定 doc_id
            res = await self.qdrant_client.delete(
                collection_name=collection,
                points_selector={"filter": {"must": [{"key": "doc_id", "match": {"value": req.doc_id}}]}},
            )
            return res.get("result", {}).get("operation_id", 1)  # 回傳刪除數量或 1
        else:
            # 刪除整個 collection
            await self.qdrant_client.delete_collection(collection_name=collection)
            return 1
