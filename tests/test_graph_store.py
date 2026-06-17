from rag import graph_store


class FakeResult:
    def __init__(self, records=None):
        self.records = records or []

    def __iter__(self):
        return iter(self.records)

    def single(self):
        return self.records[0] if self.records else None


class FakeTx:
    def __init__(self, state):
        self.state = state

    def run(self, query, **params):
        self.state["queries"].append(query)

        if "RETURN count(d) > 0 AS exists" in query:
            return FakeResult([{"exists": self.state["exists"]}])

        if "RETURN c.filing_id AS filing_id" in query:
            return FakeResult(self.state["chunks"])

        if "DETACH DELETE" in query:
            self.state["exists"] = False
            self.state["chunks"] = []
            return FakeResult()

        if "CREATE (d:Document)" in query:
            self.state["exists"] = True
            self.state["document"] = params["properties"]
            return FakeResult()

        if "SET c = $chunk" in query:
            self.state["chunks"].append(params["chunk"])
            return FakeResult()

        return FakeResult()


class FakeSession:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute_write(self, fn, *args):
        return fn(FakeTx(self.state), *args)

    def execute_read(self, fn, *args):
        return fn(FakeTx(self.state), *args)


class FakeDriver:
    def __init__(self):
        self.state = {"exists": False, "chunks": [], "queries": [], "document": None}

    def session(self, database=None):
        return FakeSession(self.state)


def test_graph_ingest_stores_document_sections_and_chunks_in_neo4j(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(graph_store, "_driver", lambda: driver)
    monkeypatch.setattr(graph_store, "_database", lambda: "neo4j")

    chunks = [
        {"chunk_index": 0, "item": "1", "section": "Business", "text": "Item 1 Business products"},
        {"chunk_index": 1, "item": "1A", "section": "Risk Factors", "text": "Item 1A Competition risk"},
    ]

    graph_store.ingest_graph_document(None, "upload-1", {"ticker": "AAPL"}, chunks)

    assert graph_store.graph_exists(None, "upload-1") is True
    assert driver.state["document"]["graph_backend"] == "neo4j"
    assert driver.state["document"]["retrieval"] == "vectorless_graph"
    assert len(driver.state["chunks"]) == 2
    assert any("HAS_SECTION" in query for query in driver.state["queries"])
    assert any("HAS_CHUNK" in query for query in driver.state["queries"])


def test_retrieve_graph_is_vectorless_and_section_aware(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(graph_store, "_driver", lambda: driver)
    monkeypatch.setattr(graph_store, "_database", lambda: "neo4j")

    driver.state["exists"] = True
    driver.state["chunks"] = [
        {
            "filing_id": "upload-1",
            "chunk_index": 0,
            "item": "1",
            "section": "Business",
            "text": "Products and services overview",
        },
        {
            "filing_id": "upload-1",
            "chunk_index": 1,
            "item": "1A",
            "section": "Risk Factors",
            "text": "Competition and supply chain risks",
        },
    ]

    results = graph_store.retrieve_graph(None, "upload-1", "What are the main risks?", top_k=1)

    assert results[0]["chunk_index"] == 1
    assert results[0]["retrieval_path"] == "neo4j_vectorless_graph"
