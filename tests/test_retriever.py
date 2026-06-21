from types import SimpleNamespace

import rag.retriever as retriever


def test_dense_search_params_uses_configured_hnsw_ef(monkeypatch):
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(QDRANT_HNSW_EF_SEARCH=192),
    )

    params = retriever._dense_search_params()

    assert params.hnsw_ef == 192
    assert params.exact is False


def test_ensure_collection_configures_hnsw_and_payload_indexes(monkeypatch):
    client = SimpleNamespace()
    client.get_collections = lambda: SimpleNamespace(collections=[])
    client.get_collection = lambda _name: SimpleNamespace(
        payload_schema={},
        config=SimpleNamespace(
            hnsw_config=SimpleNamespace(
                m=24,
                ef_construct=160,
                full_scan_threshold=5000,
            )
        ),
    )
    create_collection_calls = []
    payload_index_calls = []
    client.create_collection = lambda **kwargs: create_collection_calls.append(kwargs)
    client.create_payload_index = lambda **kwargs: payload_index_calls.append(kwargs)

    monkeypatch.setattr(retriever, "_client", lambda: client)
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(
            QDRANT_HNSW_M=24,
            QDRANT_HNSW_EF_CONSTRUCT=160,
            QDRANT_HNSW_FULL_SCAN_THRESHOLD=5000,
        ),
    )

    retriever.ensure_collection()

    hnsw = create_collection_calls[0]["hnsw_config"]
    assert hnsw.m == 24
    assert hnsw.ef_construct == 160
    assert hnsw.full_scan_threshold == 5000
    assert {call["field_name"] for call in payload_index_calls} == {"filing_id", "item"}


def test_ensure_hnsw_config_updates_existing_collection(monkeypatch):
    update_calls = []
    client = SimpleNamespace(
        get_collection=lambda _name: SimpleNamespace(
            config=SimpleNamespace(
                hnsw_config=SimpleNamespace(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=10000,
                )
            )
        ),
        update_collection=lambda **kwargs: update_calls.append(kwargs),
    )
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(
            QDRANT_HNSW_M=32,
            QDRANT_HNSW_EF_CONSTRUCT=200,
            QDRANT_HNSW_FULL_SCAN_THRESHOLD=5000,
        ),
    )

    retriever._ensure_hnsw_config(client)

    hnsw = update_calls[0]["hnsw_config"]
    assert hnsw.m == 32
    assert hnsw.ef_construct == 200
    assert hnsw.full_scan_threshold == 5000
