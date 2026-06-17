from types import SimpleNamespace

import rag.pipeline as pipeline


def test_hybrid_retrieve_keeps_existing_section_filter(monkeypatch):
    search_calls = []
    rerank_calls = []

    monkeypatch.setattr(pipeline, "_retrieval_mode", lambda: "hybrid")
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.1])
    monkeypatch.setattr(pipeline, "sparse_encode", lambda text: ([1], [1.0]))

    def fake_search(query_vector, query_sparse, filing_id, top_k, item_filter):
        search_calls.append({
            "filing_id": filing_id,
            "top_k": top_k,
            "item_filter": item_filter,
        })
        return [
            {"chunk_index": i, "filing_id": filing_id, "text": f"risk chunk {i}", "score": 0.5}
            for i in range(6)
        ]

    def fake_rerank(question, chunks, top_k):
        rerank_calls.append({"count": len(chunks), "top_k": top_k})
        return chunks[:top_k]

    monkeypatch.setattr(pipeline, "search", fake_search)
    monkeypatch.setattr(pipeline, "rerank", fake_rerank)

    chunks = pipeline.retrieve("What are the biggest risks?", "filing-1", top_k=5)

    assert len(chunks) == 3
    assert search_calls == [{"filing_id": "filing-1", "top_k": 12, "item_filter": ["1A"]}]
    assert rerank_calls == [{"count": 6, "top_k": 3}]


def test_fusion_retrieve_combines_vector_and_section_paths(monkeypatch):
    search_calls = []
    section_calls = []
    rerank_calls = []

    monkeypatch.setattr(pipeline, "_retrieval_mode", lambda: "fusion")
    monkeypatch.setattr(pipeline, "reason_sections", lambda question, filing_scope: ["7"])
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.1])
    monkeypatch.setattr(pipeline, "sparse_encode", lambda text: ([1], [1.0]))

    def fake_search(query_vector, query_sparse, filing_id, top_k, item_filter):
        search_calls.append({
            "filing_id": filing_id,
            "top_k": top_k,
            "item_filter": item_filter,
        })
        return [
            {"chunk_index": i, "filing_id": filing_id, "text": f"vector chunk {i}", "score": 0.5}
            for i in range(1, 6)
        ]

    def fake_get_section_chunks(filing_id, item, limit):
        section_calls.append({"filing_id": filing_id, "item": item, "limit": limit})
        return [
            {"chunk_index": 3, "filing_id": filing_id, "text": "duplicate section chunk", "score": 0.0},
            {"chunk_index": 8, "filing_id": filing_id, "text": "section-only chunk", "score": 0.0},
        ]

    def fake_rerank(question, chunks, top_k):
        rerank_calls.append([chunk["chunk_index"] for chunk in chunks])
        return chunks[:top_k]

    monkeypatch.setattr(pipeline, "search", fake_search)
    monkeypatch.setattr(pipeline, "get_section_chunks", fake_get_section_chunks)
    monkeypatch.setattr(pipeline, "rerank", fake_rerank)

    chunks = pipeline.retrieve("How did margins change?", "filing-1", top_k=5)

    assert len(chunks) == 5
    assert search_calls == [{"filing_id": "filing-1", "top_k": 20, "item_filter": None}]
    assert section_calls == [{"filing_id": "filing-1", "item": "7", "limit": 40}]
    assert rerank_calls == [
        [1, 2, 3, 4, 5],  # vector path top 5
        [3, 8],           # vectorless section path top 5
        [1, 2, 3, 4, 5, 8],
    ]


def test_reason_sections_uses_cache(monkeypatch):
    redis = SimpleNamespace(
        get=lambda key: '["7", "1A"]',
        setex=lambda *args: None,
    )

    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(SECTION_REASONER_CACHE_TTL_SECONDS=604800))

    def fake_get_redis():
        return redis

    import cache.redis_client

    monkeypatch.setattr(cache.redis_client, "get_redis", fake_get_redis)

    items = pipeline.reason_sections("How is the company performing?", "filing-1")

    assert items == ["7", "1A"]
