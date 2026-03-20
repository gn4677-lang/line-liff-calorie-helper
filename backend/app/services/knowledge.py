from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from math import log
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import quote_plus

import httpx

from ..config import BASE_DIR


KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PACK_REGISTRY_FILE = KNOWLEDGE_DIR / "pack_registry.json"
KNOWLEDGE_PACKET_VERSION = "knowledge-packet-v2"

CONVENIENCE_STORE_CHAINS = {"familymart", "7-eleven", "hi-life", "okmart"}
GENERIC_QUERY_TOKENS = {"food", "foods", "nutrition", "nutritional", "calorie", "calories", "kcal", "eat", "eating"}
MIN_BM25_ANSWER_SCORE = 1.5

ALIASES = {
    "7-11": "7-eleven",
    "711": "7-eleven",
    "seven": "7-eleven",
    "7 eleven": "7-eleven",
    "7eleven": "7-eleven",
    "全家": "familymart",
    "family mart": "familymart",
    "familymart": "familymart",
    "fami": "familymart",
    "萊爾富": "hi-life",
    "萊富": "hi-life",
    "hi life": "hi-life",
    "hilife": "hi-life",
    "ok便利商店": "okmart",
    "ok mart": "okmart",
    "okmart": "okmart",
    "可不可": "kebuke",
    "可不可熟成紅茶": "kebuke",
    "kebuke": "kebuke",
    "迷客夏": "milksha",
    "milksha": "milksha",
    "qburger": "q burger",
    "q burger": "q burger",
    "麥味登": "mwd",
    "mwd": "mwd",
    "八方": "eightway",
    "八方雲集": "eightway",
    "8way": "eightway",
    "eightway": "eightway",
    "肯德基": "kfc",
    "kfc": "kfc",
    "珍珠": "pearls",
    "波霸": "pearls",
    "白玉": "pearls",
    "boba": "pearls",
}

PACKAGING_CUE_PATTERNS = {
    "bento_box": ["便當", "餐盒", "bento", "rice box"],
    "rice_ball": ["御飯糰", "飯糰", "onigiri", "rice ball"],
    "sandwich_pack": ["三明治", "sandwich"],
    "salad_cup": ["沙拉", "salad"],
    "chicken_pack": ["雞胸", "舒肥雞", "chicken breast"],
    "tea_egg": ["茶葉蛋", "tea egg"],
    "sweet_potato": ["地瓜", "烤地瓜", "sweet potato"],
    "dessert_pack": ["甜點", "甜甜圈", "布丁", "donut", "dessert"],
    "drink_bottle": ["寶特瓶", "瓶裝", "bottle"],
    "drink_cup": ["杯裝", "中杯", "大杯", "cup", "ml"],
}

ABSTRACT_TERMS = {"difference", "compare", "comparison", "why", "how", "差異", "比較", "怎麼", "為什麼", "原理"}
CALORIE_QUESTION_TRIGGERS = {"kcal", "calorie", "calories", "熱量", "卡路里"}
SEARCH_TRIGGERS = {
    "ig",
    "instagram",
    "menu",
    "brand",
    "new item",
    "launch",
    "limited",
    "store",
    "shop",
    "restaurant",
    "cafe",
    "http",
    "https",
    "菜單",
    "新品",
    "新口味",
    "聯名",
    "限定",
    "門市",
    "官網",
    "店家",
    "餐廳",
}


@dataclass(frozen=True)
class PackMeta:
    pack_id: str
    path: str
    kind: str
    roles: tuple[str, ...]
    schema: str = ""
    priority: int = 50
    stability: str = "stable"
    description: str = ""
    name_fields: tuple[str, ...] = ()
    alias_fields: tuple[str, ...] = ()
    tag_fields: tuple[str, ...] = ()
    note_fields: tuple[str, ...] = ()
    risk_fields: tuple[str, ...] = ()
    serving_fields: tuple[str, ...] = ()
    chain_fields: tuple[str, ...] = ()
    kcal_field_exact: str | None = None
    kcal_field_low: str | None = None
    kcal_field_high: str | None = None


@dataclass
class KnowledgeResult:
    answer: str
    sources: list[dict[str, Any]]
    used_search: bool = False
    packet: dict[str, Any] | None = None


def answer_nutrition_question(question: str, *, allow_search: bool = True, source_hint: str | None = None) -> KnowledgeResult:
    normalized = canonicalize(question)
    hits = lookup_food_catalog(" ".join(part for part in [question, source_hint] if part))
    if should_use_catalog_answer(normalized, hits):
        top_items = hits[:3]
        return KnowledgeResult(
            answer=compose_catalog_answer(question, top_items),
            sources=[{"title": item["name"], "path": item["source_path"]} for item in top_items],
            packet={
                "match_mode": "structured",
                "matched_items": [item["name"] for item in top_items],
                "matched_packs": sorted({item["pack_id"] for item in top_items}),
            },
        )

    docs = load_knowledge_docs()
    direct_hits = direct_match_docs(normalized, docs)
    if direct_hits:
        top_docs = direct_hits[:4]
        return KnowledgeResult(
            answer=compose_local_answer(question, top_docs),
            sources=[{"title": item["title"], "path": str(item["path"])} for item in top_docs],
            packet={"match_mode": "direct", "matched_docs": [item["title"] for item in top_docs]},
        )

    ranked = rank_docs(normalized, docs)
    query_tokens = tokenize(normalized)
    top_docs = [
        item
        for item in ranked
        if item["score"] >= MIN_BM25_ANSWER_SCORE and _has_substantive_overlap(query_tokens, tokenize(item["content"]))
    ][:4]
    if top_docs:
        return KnowledgeResult(
            answer=compose_local_answer(question, top_docs),
            sources=[{"title": item["title"], "path": str(item["path"])} for item in top_docs],
            packet={"match_mode": "bm25", "matched_docs": [item["title"] for item in top_docs]},
        )

    if allow_search and should_search(question, source_hint):
        search_results = targeted_web_search(question, source_hint=source_hint)
        if search_results:
            return KnowledgeResult(
                answer=compose_search_answer(question, search_results),
                sources=search_results,
                used_search=True,
                packet={"match_mode": "search", "search_hits": [item["title"] for item in search_results]},
            )

    return KnowledgeResult(
        answer="我現在還沒有夠強的本地資料能直接回答。補上品牌、品項、配料、份量，或丟一張菜單照片，我就能再縮小範圍。",
        sources=[],
        packet={"match_mode": "none", "matched_docs": []},
    )


def build_estimation_knowledge_packet(
    query: str,
    *,
    source_hint: str | None = None,
    ocr_hits: list[dict[str, Any]] | None = None,
    meal_type: str | None = None,
    source_mode: str | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    ocr_text = " ".join(str(hit.get("text", "")) for hit in (ocr_hits or []) if hit.get("text"))
    combined = " ".join(part for part in [query, source_hint, ocr_text] if part).strip()
    packaging = infer_packaging_heuristics(query, source_hint=source_hint, ocr_hits=ocr_hits)
    hits = lookup_food_catalog(combined, limit=max(limit * 2, 12))
    grouped = _group_hits_by_pack(hits)
    chain_hints = set(packaging.get("chain_hints", []))
    query_tokens = set(tokenize(canonicalize(combined)))
    if chain_hints:
        grouped["chain_menu_cards_tw"] = [
            item
            for item in grouped.get("chain_menu_cards_tw", [])
            if item.get("chain_id") in chain_hints and _has_specific_overlap(item, query_tokens, chain_hints)
        ]
        grouped["convenience_store_skus_tw"] = [
            item
            for item in grouped.get("convenience_store_skus_tw", [])
            if item.get("chain_id") in chain_hints and _has_specific_overlap(item, query_tokens, chain_hints)
        ]
    brand_cards = lookup_brand_cards(combined, limit=3)
    visual_anchors = lookup_visual_portion_anchors(combined, limit=3)
    brand_hints = _merge_brand_hints(packaging.get("chain_hints", []), brand_cards)

    strategy = _choose_primary_strategy(grouped, combined, likely_convenience_store=packaging["likely_convenience_store"])
    primary_matches = _select_primary_matches(strategy, grouped, hits, combined, likely_convenience_store=packaging["likely_convenience_store"])
    supporting_matches = _select_supporting_matches(strategy, grouped, primary_matches)

    return {
        "version": KNOWLEDGE_PACKET_VERSION,
        "query": combined,
        "meal_type": meal_type,
        "source_mode": source_mode,
        "primary_strategy": strategy,
        "primary_matches": [_serialize_match(item) for item in primary_matches],
        "supporting_matches": [_serialize_match(item) for item in supporting_matches[:4]],
        "matched_packs": sorted({item["pack_id"] for item in [*primary_matches, *supporting_matches]}),
        "brand_hints": brand_hints,
        "brand_cards": [{"title": item["title"], "path": str(item["path"]), "score": item.get("score", 0)} for item in brand_cards],
        "visual_anchors": [
            {
                "name": item["name"],
                "anchor_id": item.get("anchor_id", ""),
                "display_name": item.get("display_name", ""),
                "source_path": item["source_path"],
                "score": item.get("_score", 0),
            }
            for item in visual_anchors
        ],
        "risk_cues": _risk_cues_from_matches(primary_matches, supporting_matches),
        "followup_slots": _followup_slots(strategy, primary_matches, combined),
        "instruction_hints": _instruction_hints(strategy, primary_matches),
        "packaging_cues": packaging["packaging_cues"],
        "likely_convenience_store": packaging["likely_convenience_store"],
    }


def build_suggested_update_packet(query: str, *, source_hint: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    packet = build_estimation_knowledge_packet(query, source_hint=source_hint, limit=6)
    suggested_update, sources = _packet_to_suggested_update(packet)
    if suggested_update:
        return suggested_update, sources
    if should_search(query, source_hint):
        results = targeted_web_search(query, source_hint=source_hint)
        if results:
            return None, results
    return None, []


def lookup_food_catalog(query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    normalized_query = canonicalize(query)
    query_tokens = tokenize(normalized_query)
    ranked: list[dict[str, Any]] = []
    for item in load_structured_catalog_items():
        aliases = item["_search_terms"]
        alias_tokens = item["_token_set"]
        score = 0.0
        exact = False
        for alias in aliases:
            if alias and alias in normalized_query:
                score += 5
                exact = True
        for token in query_tokens:
            if token in alias_tokens:
                score += 2
            elif any(token in alias for alias in aliases):
                score += 1
        if _looks_like_calorie_question(normalized_query):
            score += 1
        score += item["pack_priority"] / 100
        if score > 0:
            ranked.append({**item, "_score": round(score, 3), "_match_type": "exact" if exact else "partial"})
    ranked.sort(key=lambda row: row["_score"], reverse=True)
    return ranked[:limit]


def lookup_visual_portion_anchors(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    normalized_query = canonicalize(query)
    query_tokens = tokenize(normalized_query)
    ranked: list[dict[str, Any]] = []
    for item in load_json_records("visual_portion_anchors_tw.json"):
        aliases = [canonicalize(name) for name in _collect_values(item, ["name", "display_name", "anchor_id", "aliases", "typical_foods"]) if name]
        alias_tokens = {token for alias in aliases for token in tokenize(alias)}
        score = 0
        for alias in aliases:
            if alias and alias in normalized_query:
                score += 4
        for token in query_tokens:
            if token in alias_tokens:
                score += 2
            elif any(token in alias for alias in aliases):
                score += 1
        if score:
            ranked.append({**item, "_score": score, "source_path": str(KNOWLEDGE_DIR / "visual_portion_anchors_tw.json")})
    ranked.sort(key=lambda row: row["_score"], reverse=True)
    return ranked[:limit]


def infer_packaging_heuristics(
    query: str,
    *,
    source_hint: str | None = None,
    ocr_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ocr_text = " ".join(str(hit.get("text", "")) for hit in (ocr_hits or []) if hit.get("text"))
    combined = canonicalize(" ".join(part for part in [query, source_hint or "", ocr_text] if part))
    chain_hints = [chain for chain in sorted(set(ALIASES.values())) if chain in combined]
    packaging_cues = [
        cue
        for cue, patterns in PACKAGING_CUE_PATTERNS.items()
        if any(canonicalize(pattern) in combined for pattern in patterns)
    ]
    likely_convenience_store = bool(set(chain_hints) & CONVENIENCE_STORE_CHAINS) or any(
        cue in {"rice_ball", "salad_cup", "chicken_pack", "tea_egg", "sweet_potato"} for cue in packaging_cues
    )
    return {
        "combined_query": combined,
        "chain_hints": chain_hints,
        "packaging_cues": packaging_cues,
        "likely_convenience_store": likely_convenience_store,
    }


def ground_brand_menu_context(
    query: str,
    *,
    source_hint: str | None = None,
    ocr_hits: list[dict[str, Any]] | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    packet = build_estimation_knowledge_packet(query, source_hint=source_hint, ocr_hits=ocr_hits, limit=max(limit, 3))
    hits = lookup_food_catalog(packet["query"], limit=max(limit * 4, 12))
    grouped = _group_hits_by_pack(hits)
    suggested_update, sources = _packet_to_suggested_update(packet)
    brand_card_sources = [{"title": item["title"], "path": str(item["path"])} for item in packet["brand_cards"]]

    return {
        "query": packet["query"],
        "catalog_matches": [_format_grounding_item(item) for item in grouped.get("food_catalog_tw", [])[:limit]],
        "menu_card_matches": [_format_grounding_item(item) for item in grouped.get("chain_menu_cards_tw", [])[:limit]],
        "convenience_store_sku_matches": [_format_grounding_item(item) for item in grouped.get("convenience_store_skus_tw", [])[:limit]],
        "convenience_store_archetype_matches": [_format_grounding_item(item) for item in grouped.get("convenience_store_archetypes_tw", [])[:limit]],
        "ramen_shop_matches": [_format_grounding_item(item) for item in grouped.get("ramen_shop_profiles_tw", [])[:limit]],
        "ramen_rule_matches": [_format_grounding_item(item) for item in grouped.get("ramen_estimation_rules_tw", [])[:limit]],
        "fried_component_matches": [_format_grounding_item(item) for item in grouped.get("fried_item_components_tw", [])[:limit]],
        "luwei_component_matches": [_format_grounding_item(item) for item in grouped.get("luwei_components_tw", [])[:limit]],
        "visual_portion_anchor_hits": packet["visual_anchors"],
        "brand_cards": packet["brand_cards"],
        "brand_hints": packet["brand_hints"],
        "packaging_cues": packet["packaging_cues"],
        "likely_convenience_store": packet["likely_convenience_store"],
        "grounding_type": _grounding_type_from_packet(packet),
        "suggested_update": suggested_update or {},
        "sources": _dedupe_sources([*sources, *brand_card_sources]),
        "estimation_packet": packet,
    }


def lookup_brand_cards(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    normalized = canonicalize(query)
    brand_docs = [doc for doc in load_knowledge_docs() if "brand_cards" in str(doc["path"]).lower()]
    if not brand_docs:
        return []
    direct = direct_match_docs(normalized, brand_docs)
    if direct:
        direct.sort(key=lambda item: item.get("score", 0), reverse=True)
        return direct[:limit]
    ranked = rank_docs(normalized, brand_docs)
    return [item for item in ranked if item.get("score", 0) > 0][:limit]


def direct_match_docs(query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for doc in docs:
        title = canonicalize(doc["title"])
        if title and title in query:
            hits.append({**doc, "score": 999.0})
    return hits


def should_use_catalog_answer(normalized_question: str, hits: list[dict[str, Any]]) -> bool:
    if not hits:
        return False
    top_score = hits[0]["_score"]
    if top_score >= 5:
        return True
    if any(term in normalized_question for term in ABSTRACT_TERMS):
        return False
    return top_score >= 2.5


def canonicalize(text: str) -> str:
    normalized = text.strip().lower()
    for alias in sorted(ALIASES, key=len, reverse=True):
        alias_lower = alias.lower()
        canonical = ALIASES[alias].lower()
        if alias_lower.isascii():
            normalized = re.sub(rf"(?<![0-9a-z]){re.escape(alias_lower)}(?![0-9a-z])", canonical, normalized)
        else:
            normalized = normalized.replace(alias_lower, canonical)
    return normalized


@lru_cache(maxsize=1)
def load_pack_registry() -> list[PackMeta]:
    payload = json.loads(PACK_REGISTRY_FILE.read_text(encoding="utf-8"))
    packs: list[PackMeta] = []
    for raw in payload.get("packs", []):
        packs.append(
            PackMeta(
                pack_id=raw["pack_id"],
                path=raw["path"],
                kind=raw["kind"],
                roles=tuple(raw.get("roles", [])),
                schema=raw.get("schema", ""),
                priority=int(raw.get("priority", 50)),
                stability=raw.get("stability", "stable"),
                description=raw.get("description", ""),
                name_fields=tuple(raw.get("name_fields", [])),
                alias_fields=tuple(raw.get("alias_fields", [])),
                tag_fields=tuple(raw.get("tag_fields", [])),
                note_fields=tuple(raw.get("note_fields", [])),
                risk_fields=tuple(raw.get("risk_fields", [])),
                serving_fields=tuple(raw.get("serving_fields", [])),
                chain_fields=tuple(raw.get("chain_fields", [])),
                kcal_field_exact=raw.get("kcal_field_exact"),
                kcal_field_low=raw.get("kcal_field_low"),
                kcal_field_high=raw.get("kcal_field_high"),
            )
        )
    return packs


def list_knowledge_packs() -> list[dict[str, Any]]:
    summary = []
    for meta in load_pack_registry():
        paths = _resolve_pack_paths(meta)
        record_count = 0
        if meta.kind == "structured_json":
            record_count = sum(len(load_json_records(path.name)) for path in paths)
        elif meta.kind in {"retrieval_doc", "brand_card"}:
            record_count = len(paths)
        summary.append(
            {
                "pack_id": meta.pack_id,
                "kind": meta.kind,
                "roles": list(meta.roles),
                "priority": meta.priority,
                "stability": meta.stability,
                "paths": [str(path) for path in paths],
                "record_count": record_count,
            }
        )
    return summary


def prewarm_knowledge_layer() -> dict[str, int]:
    registry = load_pack_registry()
    docs = load_knowledge_docs()
    structured_items = load_structured_catalog_items()
    return {
        "pack_count": len(registry),
        "doc_count": len(docs),
        "structured_item_count": len(structured_items),
    }


def knowledge_runtime_status() -> dict[str, Any]:
    prewarmed = prewarm_knowledge_layer()
    latest_source_mtime = 0.0
    pack_ids: list[str] = []
    for meta in load_pack_registry():
        pack_ids.append(meta.pack_id)
        for path in _resolve_pack_paths(meta):
            try:
                latest_source_mtime = max(latest_source_mtime, path.stat().st_mtime)
            except OSError:
                continue
    return {
        "version": KNOWLEDGE_PACKET_VERSION,
        "pack_ids": pack_ids,
        "latest_source_mtime": latest_source_mtime,
        **prewarmed,
    }


def refresh_knowledge_layer() -> dict[str, Any]:
    load_pack_registry.cache_clear()
    load_knowledge_docs.cache_clear()
    load_json_records.cache_clear()
    load_structured_catalog_items.cache_clear()
    return knowledge_runtime_status()


@lru_cache(maxsize=1)
def load_knowledge_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for meta in load_pack_registry():
        for path in _resolve_pack_paths(meta):
            if meta.kind == "structured_json":
                docs.extend(_load_structured_docs(meta, path))
            else:
                content = path.read_text(encoding="utf-8")
                docs.append({"title": path.stem, "path": path, "content": content})
    return docs


@lru_cache(maxsize=32)
def load_json_records(file_name: str) -> list[dict[str, Any]]:
    path = KNOWLEDGE_DIR / file_name
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _load_structured_docs(meta: PackMeta, path: Path) -> list[dict[str, Any]]:
    docs = []
    for index, item in enumerate(load_json_records(path.name)):
        title = _first_nonempty(*_collect_values(item, meta.name_fields)) or f"{meta.pack_id}-{index}"
        docs.append({"title": title, "path": path, "content": json.dumps(item, ensure_ascii=False)})
    return docs


@lru_cache(maxsize=1)
def load_structured_catalog_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for meta in load_pack_registry():
        if meta.kind != "structured_json":
            continue
        for path in _resolve_pack_paths(meta):
            for item in load_json_records(path.name):
                normalized = _normalize_structured_lookup_item(item, meta, path)
                if normalized is not None:
                    items.append(normalized)
    return items


def _normalize_structured_lookup_item(item: dict[str, Any], meta: PackMeta, path: Path) -> dict[str, Any] | None:
    low, high = _extract_kcal_range(item, meta)
    if low is None and high is None:
        return None

    name = _first_nonempty(*_collect_values(item, meta.name_fields))
    if not name:
        return None

    aliases = _collect_values(item, meta.alias_fields)
    tags = _collect_values(item, meta.tag_fields)
    notes = " | ".join(value for value in _collect_values(item, meta.note_fields) if value)
    risk_flags = _collect_values(item, meta.risk_fields)
    serving = _first_nonempty(*_collect_values(item, meta.serving_fields), "1 serving")
    chain_id = _first_nonempty(*_collect_values(item, meta.chain_fields))
    search_terms = [canonicalize(value) for value in [name, *aliases, *tags, *(chain_id and [chain_id] or [])] if value]

    return {
        **item,
        "name": name,
        "aliases": aliases,
        "tags": tags,
        "notes": notes,
        "risk_flags": risk_flags,
        "typical_serving": serving,
        "typical_kcal_low": int(low if low is not None else high or 0),
        "typical_kcal_high": int(high if high is not None else low or 0),
        "chain_id": chain_id,
        "pack_id": meta.pack_id,
        "pack_kind": meta.kind,
        "pack_roles": list(meta.roles),
        "pack_priority": meta.priority,
        "source_path": str(path),
        "_search_terms": search_terms,
        "_token_set": {token for term in search_terms for token in tokenize(term)},
    }


def _extract_kcal_range(item: dict[str, Any], meta: PackMeta) -> tuple[int | None, int | None]:
    if meta.kcal_field_exact:
        exact = _extract_number(item.get(meta.kcal_field_exact))
        if exact is not None:
            rounded = int(round(exact))
            return rounded, rounded

    low = _extract_number(item.get(meta.kcal_field_low)) if meta.kcal_field_low else None
    high = _extract_number(item.get(meta.kcal_field_high)) if meta.kcal_field_high else None
    if low is None and high is None:
        return None, None
    if low is None:
        low = high
    if high is None:
        high = low
    return int(round(low or 0)), int(round(high or 0))


def rank_docs(query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    doc_tokens = [tokenize(doc["content"]) for doc in docs]
    avgdl = sum(len(tokens) for tokens in doc_tokens) / max(len(doc_tokens), 1)
    rankings = []
    for doc, tokens in zip(docs, doc_tokens):
        rankings.append({**doc, "score": bm25_score(query_tokens, tokens, doc_tokens, avgdl)})
    rankings.sort(key=lambda item: item["score"], reverse=True)
    return rankings


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", text.lower()) if token]


def _has_substantive_overlap(query_tokens: list[str], doc_tokens: list[str]) -> bool:
    substantive = [token for token in query_tokens if _is_substantive_token(token)]
    if not substantive:
        return False
    doc_token_set = set(doc_tokens)
    return any(token in doc_token_set for token in substantive)


def _is_substantive_token(token: str) -> bool:
    if token.isdigit() or token in GENERIC_QUERY_TOKENS:
        return False
    if token.isascii() and len(token) < 3:
        return False
    return True


def bm25_score(query_tokens: list[str], doc_tokens: list[str], corpus_tokens: list[list[str]], avgdl: float) -> float:
    if not doc_tokens:
        return 0.0
    score = 0.0
    doc_len = len(doc_tokens)
    k1 = 1.5
    b = 0.75
    for token in query_tokens:
        freq = doc_tokens.count(token)
        if freq == 0:
            continue
        containing = sum(1 for tokens in corpus_tokens if token in tokens)
        idf = log((len(corpus_tokens) - containing + 0.5) / (containing + 0.5) + 1)
        score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * doc_len / max(avgdl, 1)))
    return round(score, 4)


def compose_local_answer(question: str, docs: list[dict[str, Any]]) -> str:
    lead = f"Here is the strongest local knowledge-pack answer I found for `{question}`:"
    bullets = [f"- {doc['title']}: {summarize_doc(doc['content'])}" for doc in docs[:3]]
    tail = "If you want a tighter estimate, add the brand, bowl type, toppings, size, or combo details."
    return "\n".join([lead, *bullets, tail])


def compose_catalog_answer(question: str, items: list[dict[str, Any]]) -> str:
    top = items[0]
    low = int(top["typical_kcal_low"])
    high = int(top["typical_kcal_high"])
    serving = top.get("typical_serving") or "1 serving"
    kcal_text = f"{low} kcal" if low == high else f"{low}-{high} kcal"
    lines = [f"Based on the local knowledge pack, `{top['name']}` is about {kcal_text} per {serving}."]
    if top.get("pack_id"):
        lines.append(f"Matched pack: {top['pack_id']}.")
    risk_flags = ", ".join(_listify(top.get("risk_flags")))
    if risk_flags:
        lines.append(f"Risk cues: {risk_flags}.")
    if top.get("notes"):
        lines.append(f"Note: {top['notes']}")
    related = [item["name"] for item in items[1:3] if item.get("name")]
    if related:
        lines.append(f"Related local matches: {', '.join(related)}.")
    lines.append("If the order had add-ons, combo sides, broth changes, or different sizes, the final total can move materially.")
    return "\n".join(lines)


def summarize_doc(content: str, limit: int = 110) -> str:
    compact = " ".join(content.split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def should_search(question: str, source_hint: str | None = None) -> bool:
    text = canonicalize(f"{question} {source_hint or ''}")
    return any(trigger in text for trigger in SEARCH_TRIGGERS)


def targeted_web_search(question: str, *, source_hint: str | None = None) -> list[dict[str, Any]]:
    query = " ".join(part for part in [question, source_hint] if part).strip()
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = httpx.get(url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return []

    matches = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    results = []
    for href, title in matches[:3]:
        clean_title = re.sub(r"<.*?>", "", title)
        results.append({"title": clean_title.strip(), "url": href, "snippet": "Matched targeted search result."})
    return results


def compose_search_answer(question: str, results: list[dict[str, Any]]) -> str:
    lines = [f"I could not answer `{question}` from the local pack, but I found a few targeted web results:"]
    for item in results[:3]:
        lines.append(f"- {item['title']}")
    lines.append("Use these as a live lookup, not as permanent local knowledge.")
    return "\n".join(lines)


def _group_hits_by_pack(hits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in hits:
        grouped.setdefault(item["pack_id"], []).append(item)
    return grouped


def _choose_primary_strategy(grouped: dict[str, list[dict[str, Any]]], combined: str, *, likely_convenience_store: bool) -> str:
    if grouped.get("chain_menu_cards_tw") or grouped.get("convenience_store_skus_tw"):
        return "exact_item"
    if likely_convenience_store and grouped.get("convenience_store_archetypes_tw"):
        return "archetype_range"
    if (grouped.get("fried_item_components_tw") or grouped.get("luwei_components_tw")) and any(
        token in combined for token in ["鹽酥雞", "炸", "fried", "滷味", "麻辣燙", "滷", "王子麵", "豆皮", "雞皮"]
    ):
        return "component_sum"
    if grouped.get("ramen_shop_profiles_tw") and any(token in combined for token in ["拉麵", "ramen", "豚骨", "雞白湯", "味噌", "沾麵", "湯頭"]):
        return "shop_profile"
    if grouped.get("ramen_estimation_rules_tw") and any(token in combined for token in ["拉麵", "ramen", "豚骨", "雞白湯", "味噌", "沾麵", "湯頭"]):
        return "broth_rule"
    if grouped.get("food_catalog_tw"):
        return "exact_item"
    return "generic"


def _select_primary_matches(
    strategy: str,
    grouped: dict[str, list[dict[str, Any]]],
    hits: list[dict[str, Any]],
    combined: str,
    *,
    likely_convenience_store: bool,
) -> list[dict[str, Any]]:
    if strategy == "exact_item":
        candidates = [*grouped.get("chain_menu_cards_tw", []), *grouped.get("convenience_store_skus_tw", []), *grouped.get("food_catalog_tw", [])]
        return _top_distinct_matches(candidates, max_items=3, allow_multiple=_looks_like_multi_item_query(combined))
    if strategy == "archetype_range":
        return grouped.get("convenience_store_archetypes_tw", [])[:1]
    if strategy == "shop_profile":
        return grouped.get("ramen_shop_profiles_tw", [])[:1]
    if strategy == "broth_rule":
        return grouped.get("ramen_estimation_rules_tw", [])[:1]
    if strategy == "component_sum":
        fried_signals = any(token in combined for token in ["鹽酥雞", "炸", "fried", "雞皮", "雞排", "甜不辣"])
        luwei_signals = any(token in combined for token in ["滷味", "麻辣燙", "王子麵", "冬粉", "鴨血", "海帶", "百頁"])
        if fried_signals and not luwei_signals:
            candidates = [*grouped.get("fried_item_components_tw", []), *grouped.get("food_catalog_tw", [])]
        elif luwei_signals and not fried_signals:
            candidates = grouped.get("luwei_components_tw", [])
        else:
            candidates = [*grouped.get("fried_item_components_tw", []), *grouped.get("luwei_components_tw", [])]
        return _top_distinct_matches(candidates, max_items=5, allow_multiple=True)
    if likely_convenience_store and grouped.get("convenience_store_archetypes_tw"):
        return grouped.get("convenience_store_archetypes_tw", [])[:1]
    return hits[:1]


def _select_supporting_matches(
    strategy: str,
    grouped: dict[str, list[dict[str, Any]]],
    primary_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    primary_keys = {(item["pack_id"], item["name"]) for item in primary_matches}
    candidates: list[dict[str, Any]] = []
    if strategy == "shop_profile":
        candidates.extend(grouped.get("ramen_estimation_rules_tw", [])[:1])
    elif strategy == "broth_rule":
        candidates.extend(grouped.get("ramen_shop_profiles_tw", [])[:1])
    else:
        candidates.extend(grouped.get("food_catalog_tw", [])[:2])
    return [item for item in candidates if (item["pack_id"], item["name"]) not in primary_keys]


def _packet_to_suggested_update(packet: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    primary = packet.get("primary_matches", [])
    if not primary:
        return None, []
    low = sum(int(item.get("kcal_low") or 0) for item in primary)
    high = sum(int(item.get("kcal_high") or 0) for item in primary)
    if low == 0 and high == 0:
        return None, []

    strategy = packet.get("primary_strategy", "generic")
    grounding_type = _grounding_type_from_packet(packet)
    reason_map = {
        "chain_menu_card": "Matched a high-confidence chain menu item.",
        "convenience_store_sku": "Matched an exact convenience-store SKU.",
        "convenience_store_archetype": "Matched a stable convenience-store archetype.",
        "catalog": "Matched a local fallback knowledge card.",
        "ramen_shop_profile": "Matched a ramen shop profile and used the representative bowl range.",
        "ramen_rule": "Matched a ramen broth rule and used the style-level range.",
        "component_sum": "Matched multiple component cards and summed them.",
        "generic": "Matched a local fallback knowledge card.",
    }
    names = [item["name"] for item in primary]
    sources = [{"title": item["name"], "path": item["source_path"]} for item in primary]
    return (
        {
            "suggested_kcal": round((low + high) / 2),
            "suggested_range": {"low": low, "high": high},
            "reason": reason_map.get(grounding_type, reason_map["generic"]),
            "sources": sources,
            "store_name": primary[0].get("chain_id") or names[0],
            "grounding_type": grounding_type,
            "matched_items": names,
            "packaging_cues": packet.get("packaging_cues", []),
        },
        sources,
    )


def _top_distinct_matches(items: list[dict[str, Any]], *, max_items: int, allow_multiple: bool) -> list[dict[str, Any]]:
    if not items:
        return []
    threshold = items[0]["_score"] - (8 if allow_multiple else 2)
    results = []
    seen = set()
    for item in items:
        key = (item["pack_id"], item["name"])
        if key in seen:
            continue
        if not allow_multiple and results:
            break
        if item["_score"] < threshold and results:
            break
        seen.add(key)
        results.append(item)
        if len(results) >= max_items:
            break
    return results


def _looks_like_multi_item_query(text: str) -> bool:
    return any(token in text for token in [",", "+", " and ", " with ", "跟", "還有", "加"])


def _followup_slots(strategy: str, primary_matches: list[dict[str, Any]], combined: str) -> list[str]:
    if strategy in {"shop_profile", "broth_rule"}:
        return ["broth_style", "oil_level", "extra_noodles", "extra_toppings"]
    if strategy == "component_sum":
        return ["portion", "oil_level", "sauce", "main_components"]
    if strategy == "archetype_range":
        return ["size", "combo_items"]
    if strategy == "exact_item" and _looks_like_multi_item_query(combined):
        return ["portion", "combo_items"]
    return ["portion"] if primary_matches else []


def _instruction_hints(strategy: str, primary_matches: list[dict[str, Any]]) -> list[str]:
    if strategy in {"shop_profile", "broth_rule"}:
        return [
            "Estimate ramen by separating noodles, broth richness, aroma oil, protein toppings, and extras.",
            "Clear shoyu/shio bowls should stay materially lower than tonkotsu, chicken paitan, or heavy miso.",
            "Backfat, butter, extra chashu, extra noodles, and rice should be added explicitly.",
        ]
    if strategy == "component_sum":
        return [
            "For Taiwanese fried snacks and luwei, sum the visible components instead of using one bundle average.",
            "Widen the range when coating thickness, residual oil, sauce, or broth intake is unclear.",
        ]
    if strategy == "archetype_range":
        return ["Prefer the stable convenience-store archetype range unless an exact SKU is visible."]
    if primary_matches:
        return ["Use the exact local match first and only widen the range for size, toppings, or combo uncertainty."]
    return ["Use a broad fallback range and ask only for the biggest missing detail."]


def _risk_cues_from_matches(*groups: Iterable[dict[str, Any]]) -> list[str]:
    cues = []
    seen = set()
    for item in [entry for group in groups for entry in group]:
        for risk in _listify(item.get("risk_flags")):
            if risk not in seen:
                seen.add(risk)
                cues.append(risk)
    return cues[:8]


def _serialize_match(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "pack_id": item["pack_id"],
        "chain_id": item.get("chain_id"),
        "kcal_low": item["typical_kcal_low"],
        "kcal_high": item["typical_kcal_high"],
        "serving": item.get("typical_serving"),
        "notes": item.get("notes", ""),
        "risk_flags": _listify(item.get("risk_flags")),
        "source_path": item["source_path"],
        "score": item.get("_score", 0),
    }


def _format_grounding_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "pack_id": item["pack_id"],
        "chain_id": item.get("chain_id"),
        "kcal_low": item["typical_kcal_low"],
        "kcal_high": item["typical_kcal_high"],
        "serving": item.get("typical_serving"),
        "notes": item.get("notes", ""),
        "source_path": item["source_path"],
        "score": item.get("_score", 0),
    }


def _merge_brand_hints(chain_hints: list[str], brand_cards: list[dict[str, Any]]) -> list[str]:
    hints = []
    for hint in chain_hints:
        if hint and hint not in hints:
            hints.append(hint)
    for card in brand_cards:
        hint = _brand_name_from_doc(card["title"])
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _has_specific_overlap(item: dict[str, Any], query_tokens: set[str], chain_hints: set[str]) -> bool:
    ignored = {token for token in chain_hints if token}
    item_tokens = {
        token
        for token in item.get("_token_set", set())
        if token not in ignored and _is_substantive_token(token)
    }
    query_specific = {token for token in query_tokens if token not in ignored and _is_substantive_token(token)}
    return bool(item_tokens & query_specific)


def _grounding_type_from_packet(packet: dict[str, Any]) -> str:
    primary = packet.get("primary_matches", [])
    if not primary:
        return "unknown"
    pack_id = primary[0].get("pack_id")
    if pack_id == "chain_menu_cards_tw":
        return "chain_menu_card"
    if pack_id == "convenience_store_skus_tw":
        return "convenience_store_sku"
    if pack_id == "convenience_store_archetypes_tw":
        return "convenience_store_archetype"
    if pack_id == "ramen_shop_profiles_tw":
        return "ramen_shop_profile"
    if pack_id == "ramen_estimation_rules_tw":
        return "ramen_rule"
    if packet.get("primary_strategy") == "component_sum":
        return "component_sum"
    return "catalog"


def _resolve_pack_paths(meta: PackMeta) -> list[Path]:
    if any(symbol in meta.path for symbol in "*?["):
        return sorted(KNOWLEDGE_DIR.glob(meta.path))
    return [KNOWLEDGE_DIR / meta.path]


def _collect_values(item: dict[str, Any], fields: Iterable[str]) -> list[str]:
    values = []
    for field in fields:
        values.extend(_listify(item.get(field)))
    return values


def _extract_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _looks_like_calorie_question(query: str) -> bool:
    return any(trigger in query for trigger in CALORIE_QUESTION_TRIGGERS)


def _brand_name_from_doc(title: str) -> str:
    normalized = title.replace("-taiwan", "").replace("-", " ").strip()
    return normalized[:80]


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in sources:
        key = (str(item.get("title", "")), str(item.get("path") or item.get("url") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _listify(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
