"""
Vector indexing and retrieval service.
"""

import time
import uuid as uuidlib
from typing import Any, Dict, List

from ..models import Citation, IndexChunksReq, RetrieveHit, RetrieveReq, SearchReq, Subgraph, SubgraphEdge, SubgraphNode
from ..repositories import ensure_qdrant_collection, get_litellm_client, get_neo4j_driver, get_qdrant_client
from ..utils import sha1


class VectorService:
    """Service for vector indexing, search, and hybrid retrieval."""

    def __init__(self):
        self.client = get_litellm_client()

    def index_chunks(self, req: IndexChunksReq) -> Dict[str, Any]:
        """
        Index text chunks into Qdrant vector database.

        Args:
            req: Index request with chunks and collection name

        Returns:
            Dict with 'ok', 'upserted', 'dim', and 'collection' keys
        """
        if not req.chunks:
            raise ValueError("chunks must be non-empty")

        # 1) Generate embeddings
        texts = [c.text for c in req.chunks]
        emb = self.client.embeddings.create(model="local-embed", input=texts)
        vectors = [d.embedding for d in emb.data]
        dim = len(vectors[0]) if vectors else 0

        # 2) Upsert to Qdrant
        qc = get_qdrant_client()
        ensure_qdrant_collection(qc, req.collection, dim)

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
            }
            points.append(PointStruct(id=pid, vector=vec, payload=payload))

        qc.upsert(collection_name=req.collection, points=points)
        return {"ok": True, "upserted": len(points), "dim": dim, "collection": req.collection}

    def search(self, req: SearchReq) -> Dict[str, Any]:
        """
        Vector similarity search.

        Args:
            req: Search request with query and filters

        Returns:
            Dict with 'ok' and 'hits' keys
        """
        # Generate query embedding
        emb = self.client.embeddings.create(model="local-embed", input=[req.query])
        qvec = emb.data[0].embedding

        # Search Qdrant
        qc = get_qdrant_client()
        import importlib

        models_mod = importlib.import_module("qdrant_client.models")
        Filter = getattr(models_mod, "Filter")

        flt = None
        if req.filters:
            flt = Filter.from_dict(req.filters)

        results = qc.search(collection_name=req.collection, query_vector=qvec, limit=req.top_k, query_filter=flt)

        hits = []
        for r in results:
            hits.append({"id": getattr(r, "id", None), "score": r.score, "payload": r.payload or {}})

        return {"ok": True, "hits": hits}

    def retrieve(self, req: RetrieveReq) -> Dict[str, Any]:
        """
        Hybrid retrieval: vector search + graph neighborhood expansion.

        Args:
            req: Retrieve request with query and options

        Returns:
            Dict with 'ok', 'hits', 'subgraph', and 'query_time_ms' keys
        """
        start_time = time.time()

        # 1) Vector search
        vector_hits = []
        try:
            emb = self.client.embeddings.create(model="local-embed", input=[req.query])
            qvec = emb.data[0].embedding

            qc = get_qdrant_client()
            import importlib

            models_mod = importlib.import_module("qdrant_client.models")
            Filter = getattr(models_mod, "Filter")

            flt = None
            if req.filters:
                flt = Filter.from_dict(req.filters)

            results = qc.search(collection_name=req.collection, query_vector=qvec, limit=req.top_k, query_filter=flt)

            for r in results:
                payload = r.payload or {}
                citation = Citation(source="vector", doc_id=payload.get("doc_id"), score=r.score)
                hit = RetrieveHit(
                    text=payload.get("text", ""),
                    metadata=payload.get("metadata", {}),
                    citations=[citation],
                    score=r.score,
                )
                vector_hits.append(hit)
        except Exception:
            pass  # Continue without vector results

        # 2) Graph expansion
        subgraph_data = None
        if req.include_subgraph:
            subgraph_data = self._expand_graph_neighborhood(req.query, req.max_hops)

        query_time = int((time.time() - start_time) * 1000)

        return {
            "ok": True,
            "hits": vector_hits,
            "subgraph": subgraph_data.model_dump() if subgraph_data else None,
            "query_time_ms": query_time,
        }

    def _expand_graph_neighborhood(self, query: str, max_hops: int) -> Subgraph | None:
        """Expand graph neighborhood based on query keywords."""
        try:
            driver = get_neo4j_driver()
            query_keywords = [kw.strip() for kw in query.lower().split() if len(kw.strip()) > 2]

            with driver.session() as session:
                # Find relevant nodes
                match_nodes = []
                for keyword in query_keywords[:3]:
                    rs = session.run(
                        """
                        MATCH (n)
                        WHERE toLower(n.id) CONTAINS $keyword
                           OR ANY(prop IN keys(n) WHERE toLower(toString(n[prop])) CONTAINS $keyword)
                        RETURN DISTINCT n.id as id, n.type as type, properties(n) as props
                        LIMIT 5
                    """,
                        keyword=keyword,
                    )
                    match_nodes.extend([record.data() for record in rs])

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
                    rs = session.run(
                        f"""
                        MATCH (a {{id: $id}})-[r]-(b)
                        RETURN
                            a.id as src_id, a.type as src_type, properties(a) as src_props,
                            type(r) as rel_type, properties(r) as rel_props,
                            b.id as dst_id, b.type as dst_type, properties(b) as dst_props,
                            startNode(r).id = $id as is_outgoing
                        LIMIT {max_hops * 10}
                    """,
                        id=node_id,
                    )

                    for record in rs:
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
