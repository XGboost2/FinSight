import sys
from types import SimpleNamespace

from rag import hyper_extract


class FakeTemplate:
    @staticmethod
    def create(_name, language="en"):
        return FakeTemplate()

    def parse(self, _text):
        return SimpleNamespace(
            nodes=[
                SimpleNamespace(
                    name="SanDisk",
                    type="company",
                    description="Storage company",
                )
            ],
            edges=[
                SimpleNamespace(
                    source="SanDisk",
                    target="Western Digital",
                    type="acquired_by",
                    description="Acquisition relationship",
                )
            ],
        )


def test_extract_upload_knowledge_uses_hyperextract_template(monkeypatch):
    monkeypatch.setitem(sys.modules, "hyperextract", SimpleNamespace(Template=FakeTemplate))

    result = hyper_extract.extract_upload_knowledge(
        "SanDisk was acquired by Western Digital.",
        [{"chunk_index": 0, "text": "SanDisk was acquired by Western Digital."}],
    )

    assert result is not None
    assert "finance/ownership_graph" in result.template
    assert result.entities[0].name == "SanDisk"
    assert result.entities[0].id == "entity:sandisk"
    assert result.relations[0].source == "entity:sandisk"
    assert result.relations[0].target == "entity:western digital"
    assert result.relations[0].type == "acquired_by"
