"""Optional Hyper-Extract integration for uploaded-document graph enrichment.

FinSight keeps upload retrieval vectorless in Neo4j. Hyper-Extract is used here
only for its structured extraction layer: entities and relations are extracted
from uploaded chunks, then persisted into the Neo4j document graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    id: str
    name: str
    type: str = ""
    description: str = ""
    chunk_index: int | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelation:
    source: str
    target: str
    type: str
    description: str = ""
    chunk_index: int | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class HyperExtractResult:
    template: str
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)


def extract_upload_knowledge(text: str, chunks: list[dict]) -> HyperExtractResult | None:
    """Extract typed knowledge from upload chunks using Hyper-Extract.

    Returns None when disabled, unavailable, or extraction fails. Upload ingest
    must not depend on this enrichment succeeding.
    """
    settings = get_settings()
    if not settings.HYPER_EXTRACT_ENABLED:
        return None

    try:
        from hyperextract import Template
    except Exception as exc:
        logger.info("Hyper-Extract unavailable; skipping graph enrichment: %s", exc)
        return None

    template_names = _template_names(settings)
    language = settings.HYPER_EXTRACT_LANGUAGE
    max_chunks = max(1, settings.HYPER_EXTRACT_MAX_CHUNKS)

    result = HyperExtractResult(template=",".join(template_names))
    for template_name in template_names:
        try:
            template = Template.create(template_name, language=language)
        except Exception as exc:
            logger.warning("Hyper-Extract template init failed (%s): %s", template_name, exc)
            continue

        for chunk in chunks[:max_chunks]:
            chunk_text = (chunk.get("text") or "").strip()
            if not chunk_text:
                continue
            try:
                extracted = template.parse(chunk_text)
            except Exception as exc:
                logger.warning(
                    "Hyper-Extract parse failed: template=%s chunk=%s error=%s",
                    template_name,
                    chunk.get("chunk_index"),
                    exc,
                )
                continue

            chunk_index = int(chunk.get("chunk_index", 0))
            result.entities.extend(_extract_entities(extracted, chunk_index))
            result.relations.extend(_extract_relations(extracted, chunk_index))

    result.entities = _dedupe_entities(result.entities)
    result.relations = _dedupe_relations(result.relations)
    if not result.entities and not result.relations:
        return None

    logger.info(
        "Hyper-Extract enrichment complete: template=%s entities=%d relations=%d",
        result.template,
        len(result.entities),
        len(result.relations),
    )
    return result


def _template_names(settings: Any) -> list[str]:
    configured = getattr(settings, "HYPER_EXTRACT_TEMPLATES", "") or settings.HYPER_EXTRACT_TEMPLATE
    names = [name.strip() for name in configured.split(",") if name.strip()]
    return names or [settings.HYPER_EXTRACT_TEMPLATE]


def _extract_entities(extracted: Any, chunk_index: int) -> list[ExtractedEntity]:
    candidates = _first_present(extracted, ("nodes", "entities", "items"))
    if candidates is None:
        data = _to_dict(extracted)
        candidates = data.get("nodes") or data.get("entities") or data.get("items") or []

    entities: list[ExtractedEntity] = []
    for raw in _as_list(candidates):
        data = _to_dict(raw)
        name = _string(data.get("name") or data.get("id") or data.get("value") or data.get("title"))
        if not name:
            continue
        entity_type = _string(data.get("type") or data.get("label") or data.get("category"))
        description = _string(data.get("description") or data.get("summary") or data.get("details"))
        entity_id = _entity_id(name, entity_type)
        entities.append(ExtractedEntity(
            id=entity_id,
            name=name,
            type=entity_type,
            description=description,
            chunk_index=chunk_index,
            properties={k: v for k, v in data.items() if _is_scalar(v)},
        ))
    return entities


def _extract_relations(extracted: Any, chunk_index: int) -> list[ExtractedRelation]:
    candidates = _first_present(extracted, ("edges", "relations", "relationships"))
    if candidates is None:
        data = _to_dict(extracted)
        candidates = data.get("edges") or data.get("relations") or data.get("relationships") or []

    relations: list[ExtractedRelation] = []
    for raw in _as_list(candidates):
        data = _to_dict(raw)
        source = _string(data.get("source") or data.get("from") or data.get("head"))
        target = _string(data.get("target") or data.get("to") or data.get("tail"))
        relation_type = _string(data.get("type") or data.get("relation") or data.get("label") or "related_to")
        if not source or not target:
            continue
        description = _string(data.get("description") or data.get("summary") or data.get("details"))
        properties = {k: v for k, v in data.items() if _is_scalar(v)}
        properties.update({"source_name": source, "target_name": target})
        relations.append(ExtractedRelation(
            source=_entity_id(source, ""),
            target=_entity_id(target, ""),
            type=relation_type,
            description=description,
            chunk_index=chunk_index,
            properties=properties,
        ))
    return relations


def _first_present(obj: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    data: dict[str, Any] = {}
    for key in ("id", "name", "type", "label", "description", "source", "target", "relation"):
        if hasattr(value, key):
            data[key] = getattr(value, key)
    return data


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return []


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _entity_id(name: str, _entity_type: str) -> str:
    return "entity:" + " ".join(name.lower().split())


def _is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool) or value is None


def _dedupe_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    merged: dict[str, ExtractedEntity] = {}
    for entity in entities:
        existing = merged.get(entity.id)
        if existing is None:
            merged[entity.id] = entity
            continue
        if not existing.description and entity.description:
            existing.description = entity.description
        existing.properties.update({k: v for k, v in entity.properties.items() if v not in ("", None)})
    return list(merged.values())


def _dedupe_relations(relations: list[ExtractedRelation]) -> list[ExtractedRelation]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ExtractedRelation] = []
    for relation in relations:
        key = (relation.source, relation.type.lower(), relation.target)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relation)
    return deduped
