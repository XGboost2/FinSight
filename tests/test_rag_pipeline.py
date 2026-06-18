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


def test_hybrid_revenue_retrieve_includes_financial_statements(monkeypatch):
    search_calls = []

    monkeypatch.setattr(pipeline, "_retrieval_mode", lambda: "hybrid")
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.1])
    monkeypatch.setattr(pipeline, "sparse_encode", lambda text: ([1], [1.0]))

    def fake_search(query_vector, query_sparse, filing_id, top_k, item_filter):
        search_calls.append({
            "filing_id": filing_id,
            "top_k": top_k,
            "item_filter": item_filter,
        })
        return [{"chunk_index": 1, "filing_id": filing_id, "text": "net sales", "score": 0.5}]

    monkeypatch.setattr(pipeline, "search", fake_search)
    monkeypatch.setattr(pipeline, "rerank", lambda question, chunks, top_k: chunks[:top_k])

    pipeline.retrieve("Compare revenue", "filing-1", top_k=5)

    assert search_calls == [{"filing_id": "filing-1", "top_k": 12, "item_filter": ["7", "8"]}]


def test_multi_retrieve_uses_hybrid_section_filter(monkeypatch):
    search_calls = []

    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.1])
    monkeypatch.setattr(pipeline, "sparse_encode", lambda text: ([1], [1.0]))

    def fake_search_multi(query_vector, query_sparse, filing_ids, top_k, item_filter):
        search_calls.append({
            "filing_ids": filing_ids,
            "top_k": top_k,
            "item_filter": item_filter,
        })
        return [
            {"chunk_index": i, "filing_id": filing_ids[0], "text": f"risk chunk {i}", "score": 0.5}
            for i in range(5)
        ]

    monkeypatch.setattr(pipeline, "search_multi", fake_search_multi)
    monkeypatch.setattr(pipeline, "rerank", lambda question, chunks, top_k: chunks[:top_k])

    chunks = pipeline.retrieve_multi("Compare the risks", ["filing-1", "filing-2"], top_k=5)

    assert len(chunks) == 3
    assert search_calls == [{
        "filing_ids": ["filing-1", "filing-2"],
        "top_k": 12,
        "item_filter": ["1A"],
    }]
