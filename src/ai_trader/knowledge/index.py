"""Deterministic parsing, chunking, snapshot replay, and time/rights-filtered RAG retrieval."""

import hashlib
import html
import json
import math
import re
from datetime import datetime
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from ai_trader.data.archive import atomic_write
from ai_trader.knowledge.catalog import verify_content
from ai_trader.knowledge.models import (
    CHUNKER_VERSION,
    PARSER_VERSION,
    CaseResult,
    Catalog,
    Chunk,
    Document,
    EvaluationBenchmark,
    EvaluationReport,
    KnowledgeSnapshot,
    Purpose,
    SearchHit,
    SearchReport,
)

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100

INJECTION_PATTERN = re.compile(
    r"\b("
    r"ignore\s+(all\s+|previous\s+|prior\s+)?instructions|"
    r"system\s+prompt|"
    r"submit\s+(a\s+|the\s+)?(trade|order)|"
    r"execute\s+(a\s+|the\s+)?(trade|order|tool)|"
    r"override\s+risk|"
    r"disregard\s+(all\s+|previous\s+)?rules"
    r")\b",
    re.I,
)

STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "but",
        "into",
        "their",
        "they",
        "its",
        "our",
        "can",
        "may",
        "will",
        "would",
        "should",
        "could",
    }
)


def contains_instruction_like_text(text: str) -> bool:
    return bool(INJECTION_PATTERN.search(text))


def _clean_text(raw_slice: str, media_type: str) -> str:
    if media_type in ("text/html", "application/xml"):
        cleaned = re.sub(
            r"<(script|style)\b[^>]*>.*?</\1>",
            " ",
            raw_slice,
            flags=re.I | re.S,
        )
        cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.S)
        # Strip leading attribute residue when marker starts inside an opening tag
        if ">" in cleaned[:120] and "<" not in cleaned[: cleaned.find(">")]:
            cleaned = cleaned[cleaned.find(">") + 1 :]
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"<[^>]*$", " ", cleaned)
        cleaned = html.unescape(cleaned)
    else:
        cleaned = raw_slice
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_document_chunks(document: Document, root: Path) -> list[Chunk]:
    if document.rights.status != "approved" or "indexing" not in document.rights.allowed_uses:
        raise ValueError("document does not permit indexing")
    raw_text = verify_content(document, root, max_bytes=MAX_DOCUMENT_BYTES)
    positions = [(raw_text.index(location.marker), location) for location in document.locations]
    positions.sort(key=lambda item: item[0])
    chunks: list[Chunk] = []
    for idx, (pos, location) in enumerate(positions):
        next_pos = positions[idx + 1][0] if idx + 1 < len(positions) else len(raw_text)
        raw_slice = raw_text[pos:next_pos]
        section_text = _clean_text(raw_slice, document.media_type)
        if not section_text:
            raise ValueError(f"empty parsed section: {location.location_id}")
        start = 0
        chunk_index = 0
        while start < len(section_text):
            end = min(len(section_text), start + CHUNK_SIZE)
            if end < len(section_text):
                space = section_text.rfind(" ", start + CHUNK_SIZE // 2, end)
                if space != -1:
                    end = space
            piece = section_text[start:end].strip()
            if piece:
                text_sha = hashlib.sha256(piece.encode("utf-8")).hexdigest()
                identity_payload = json.dumps(
                    {
                        "version_id": document.version_id,
                        "location_id": location.location_id,
                        "chunk_index": chunk_index,
                        "char_start": start,
                        "char_end": end,
                        "parser_version": PARSER_VERSION,
                        "chunker_version": CHUNKER_VERSION,
                        "text_sha256": text_sha,
                    },
                    sort_keys=True,
                ).encode("utf-8")
                chunks.append(
                    Chunk(
                        chunk_id=hashlib.sha256(identity_payload).hexdigest(),
                        document_id=document.document_id,
                        version_id=document.version_id,
                        kind=document.kind,
                        title=document.title,
                        edition=document.edition,
                        source_url=document.source_url,
                        available_at=document.available_at,
                        allowed_uses=document.rights.allowed_uses,
                        attribution=document.rights.attribution,
                        location_id=location.location_id,
                        location_label=location.label,
                        chunk_index=chunk_index,
                        char_start=start,
                        char_end=end,
                        text=piece,
                        text_sha256=text_sha,
                        instruction_like=contains_instruction_like_text(piece),
                    )
                )
                chunk_index += 1
            if end >= len(section_text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def build_knowledge_snapshot(
    catalog: Catalog,
    root: Path,
    state_dir: Path | None = None,
) -> KnowledgeSnapshot:
    catalog_sha = hashlib.sha256(catalog.model_dump_json().encode("utf-8")).hexdigest()
    all_chunks: list[Chunk] = []
    for document in catalog.documents:
        all_chunks.extend(parse_document_chunks(document, root))
    all_chunks.sort(key=lambda c: (c.document_id, c.version_id, c.location_id, c.chunk_index))
    snapshot_payload = json.dumps(
        {
            "catalog_sha256": catalog_sha,
            "parser_version": PARSER_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "documents": [d.version_id for d in catalog.documents],
            "chunks": [c.chunk_id for c in all_chunks],
        },
        sort_keys=True,
    ).encode("utf-8")
    snapshot = KnowledgeSnapshot(
        snapshot_id=hashlib.sha256(snapshot_payload).hexdigest(),
        catalog_sha256=catalog_sha,
        documents=catalog.documents,
        chunks=tuple(all_chunks),
    )
    if state_dir is not None:
        out_dir = state_dir / "knowledge" / "snapshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{snapshot.snapshot_id}.json"
        if path.exists():
            existing = load_knowledge_snapshot(state_dir, snapshot.snapshot_id)
            if existing != snapshot:
                raise ValueError("immutable knowledge snapshot differs")
        else:
            atomic_write(path, snapshot.model_dump_json(indent=2).encode())
    return snapshot


def load_knowledge_snapshot(state_dir: Path, snapshot_id: str) -> KnowledgeSnapshot:
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
        raise ValueError("invalid snapshot_id")
    path = state_dir / "knowledge" / "snapshots" / f"{snapshot_id}.json"
    snapshot = KnowledgeSnapshot.model_validate_json(path.read_bytes())
    validate_snapshot(snapshot)
    if snapshot.snapshot_id != snapshot_id:
        raise ValueError("knowledge snapshot path/id mismatch")
    return snapshot


def validate_snapshot(snapshot: KnowledgeSnapshot) -> None:
    """Verify the complete stored envelope before retrieval; raw files are not required."""
    if (snapshot.parser_version, snapshot.chunker_version) != (PARSER_VERSION, CHUNKER_VERSION):
        raise ValueError("legacy knowledge snapshot must be rebuilt from pinned original files")
    catalog = Catalog.model_validate_json(Catalog(documents=snapshot.documents).model_dump_json())
    catalog_sha = hashlib.sha256(catalog.model_dump_json().encode()).hexdigest()
    if catalog_sha != snapshot.catalog_sha256:
        raise ValueError("knowledge catalog checksum mismatch")
    documents = {document.version_id: document for document in catalog.documents}
    identities, seen, indexed = [], set(), set()
    for chunk in snapshot.chunks:
        document = documents.get(chunk.version_id)
        if document is None:
            raise ValueError("chunk references unknown document version")
        locations = {location.location_id: location for location in document.locations}
        location = locations.get(chunk.location_id)
        if location is None or chunk.location_label != location.label:
            raise ValueError("chunk citation metadata mismatch")
        if any(
            getattr(chunk, key) != expected
            for key, expected in {
                "document_id": document.document_id,
                "kind": document.kind,
                "title": document.title,
                "edition": document.edition,
                "source_url": document.source_url,
                "available_at": document.available_at,
                "allowed_uses": document.rights.allowed_uses,
                "attribution": document.rights.attribution,
                "parser_version": snapshot.parser_version,
                "chunker_version": snapshot.chunker_version,
                "instruction_like": contains_instruction_like_text(chunk.text),
            }.items()
        ):
            raise ValueError("chunk/document metadata mismatch")
        if hashlib.sha256(chunk.text.encode()).hexdigest() != chunk.text_sha256:
            raise ValueError("chunk content checksum mismatch")
        payload = {
            key: getattr(chunk, key)
            for key in (
                "version_id",
                "location_id",
                "chunk_index",
                "char_start",
                "char_end",
                "parser_version",
                "chunker_version",
                "text_sha256",
            )
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if chunk.chunk_id != digest or digest in seen:
            raise ValueError("chunk identity mismatch or duplicate")
        identities.append(digest)
        seen.add(digest)
        indexed.add(document.version_id)
    if indexed != set(documents):
        raise ValueError("document has no indexed chunks")
    expected = hashlib.sha256(
        json.dumps(
            {
                "catalog_sha256": catalog_sha,
                "parser_version": snapshot.parser_version,
                "chunker_version": snapshot.chunker_version,
                "documents": [document.version_id for document in snapshot.documents],
                "chunks": identities,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if snapshot.snapshot_id != expected:
        raise ValueError("knowledge snapshot checksum mismatch")


def replay_knowledge_snapshot(
    state_dir: Path,
    snapshot_id: str,
    root: Path,
) -> dict:
    stored = load_knowledge_snapshot(state_dir, snapshot_id)
    rebuilt = build_knowledge_snapshot(Catalog(documents=stored.documents), root, state_dir=None)
    identical = stored == rebuilt
    return {
        "snapshot_id": stored.snapshot_id,
        "integrity": "passed" if identical else "failed",
        "replay": "identical" if identical else "mismatch",
        "documents": len(stored.documents),
        "chunks": len(stored.chunks),
        "untrusted_data_only": True,
        "historical_backtest_approved": False,
        "trading_approved": False,
    }


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{2,}", text.lower()) if token not in STOPWORDS]


def search_knowledge(
    snapshot: KnowledgeSnapshot,
    query: str,
    decision_time: datetime,
    *,
    purpose: Purpose = "model_context",
    top_k: int = 5,
) -> SearchReport:
    validate_snapshot(snapshot)
    decision_time = TypeAdapter(AwareDatetime).validate_python(decision_time)
    purpose = TypeAdapter(Purpose).validate_python(purpose)
    if top_k < 1 or top_k > 50:
        raise ValueError("top_k must be between 1 and 50")
    query_tokens = _tokenize(query)
    if not query_tokens:
        raise ValueError("query must contain at least one searchable token")

    eligible_versions: set[str] = set()
    excluded: dict[str, tuple[str, ...]] = {}
    for doc in snapshot.documents:
        reasons: list[str] = []
        if doc.rights.status != "approved" or purpose not in doc.rights.allowed_uses:
            reasons.append("usage_not_permitted")
        if doc.available_at > decision_time:
            reasons.append("unavailable_at_decision")
        if any(
            newer.supersedes == doc.version_id and newer.available_at <= decision_time
            for newer in snapshot.documents
        ):
            reasons.append("superseded_at_decision")
        key = f"{doc.document_id}@{doc.version_id[:12]}"
        if reasons:
            excluded[key] = tuple(reasons)
        else:
            eligible_versions.add(doc.version_id)

    candidate_chunks = [c for c in snapshot.chunks if c.version_id in eligible_versions]
    doc_freq: dict[str, int] = {}
    chunk_tokens: list[tuple[Chunk, list[str]]] = []
    for chunk in candidate_chunks:
        tokens = _tokenize(f"{chunk.title} {chunk.location_label} {chunk.text}")
        chunk_tokens.append((chunk, tokens))
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    total_chunks = max(len(candidate_chunks), 1)
    scored: list[tuple[float, str, Chunk]] = []
    for chunk, tokens in chunk_tokens:
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for q_term in set(query_tokens):
            tf = counts.get(q_term, 0)
            if tf > 0:
                idf = math.log(1.0 + (total_chunks / doc_freq[q_term]))
                score += (1.0 + math.log(tf)) * idf
        if score > 0:
            scored.append((round(score, 6), chunk.chunk_id, chunk))

    scored.sort(key=lambda item: (-item[0], item[1]))
    hits = tuple(
        SearchHit(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            title=chunk.title,
            edition=chunk.edition,
            source_url=chunk.source_url,
            available_at=chunk.available_at,
            attribution=chunk.attribution,
            location_id=chunk.location_id,
            location_label=chunk.location_label,
            chunk_index=chunk.chunk_index,
            score=score,
            text=chunk.text,
            text_sha256=chunk.text_sha256,
            instruction_like=chunk.instruction_like,
        )
        for score, _, chunk in scored[:top_k]
    )
    return SearchReport(
        snapshot_id=snapshot.snapshot_id,
        query=query,
        decision_time=decision_time,
        purpose=purpose,
        eligible_documents=len(eligible_versions),
        excluded_documents=excluded,
        hits=hits,
    )


def load_evaluation_benchmark(path: Path) -> EvaluationBenchmark:
    return EvaluationBenchmark.model_validate_json(path.read_bytes())


def evaluate_knowledge_benchmark(
    benchmark: EvaluationBenchmark,
    snapshot: KnowledgeSnapshot,
) -> EvaluationReport:
    results: list[CaseResult] = []
    pos_total = 0
    doc_hits = 0
    loc_hits = 0
    num_total = 0
    num_hits = 0
    guard_total = 0
    guard_hits = 0
    required_total = 0
    required_hits = 0

    for case in benchmark.cases:
        report = search_knowledge(
            snapshot,
            case.query,
            case.decision_time,
            purpose=case.purpose,
            top_k=case.top_k,
        )
        reasons: list[str] = []
        top_doc = report.hits[0].document_id if report.hits else None
        top_loc = report.hits[0].location_id if report.hits else None
        matched_subs: list[str] = []
        missing_subs: list[str] = []

        if case.expect_empty:
            guard_total += 1
            if report.hits:
                reasons.append("unexpected_hits_returned")
            if case.expected_exclusion_reason:
                all_reasons = {
                    r for doc_reasons in report.excluded_documents.values() for r in doc_reasons
                }
                if case.expected_exclusion_reason not in all_reasons:
                    reasons.append("missing_expected_exclusion_reason")
            if not reasons:
                guard_hits += 1
        else:
            pos_total += 1
            matching_hits = [
                h
                for h in report.hits
                if h.document_id == case.expected_document_id
                and h.location_id == case.expected_location_id
            ]
            if any(h.document_id == case.expected_document_id for h in report.hits):
                doc_hits += 1
            else:
                reasons.append("expected_document_not_found")
            if matching_hits:
                loc_hits += 1
            else:
                reasons.append("expected_citation_location_not_found")
            combined_text = " ".join(h.text for h in matching_hits)
            for sub in case.required_substrings:
                if sub in combined_text:
                    matched_subs.append(sub)
                else:
                    missing_subs.append(sub)
            if case.required_substrings:
                required_total += 1
                if not missing_subs:
                    required_hits += 1
                else:
                    reasons.append("missing_required_substring")
                numeric = [sub for sub in case.required_substrings if re.search(r"\d", sub)]
                if numeric:
                    num_total += 1
                    if all(sub in combined_text for sub in numeric):
                        num_hits += 1

        results.append(
            CaseResult(
                case_id=case.case_id,
                passed=not reasons,
                top_document_id=top_doc,
                top_location_id=top_loc,
                matched_substrings=tuple(matched_subs),
                missing_substrings=tuple(missing_subs),
                reasons=tuple(reasons),
            )
        )

    passed_cases = sum(1 for r in results if r.passed)
    hit_rate = round(doc_hits / pos_total, 4) if pos_total else None
    citation_acc = round(loc_hits / pos_total, 4) if pos_total else None
    numeric_acc = round(num_hits / num_total, 4) if num_total else None
    temporal_acc = round(guard_hits / guard_total, 4) if guard_total else None
    status = "passed" if passed_cases == len(results) else "blocked"

    return EvaluationReport(
        benchmark_id=benchmark.benchmark_id,
        snapshot_id=snapshot.snapshot_id,
        status=status,
        total_cases=len(results),
        passed_cases=passed_cases,
        hit_rate=hit_rate,
        citation_accuracy=citation_acc,
        numeric_accuracy=numeric_acc,
        temporal_guard_accuracy=temporal_acc,
        required_text_accuracy=round(required_hits / required_total, 4) if required_total else None,
        numeric_cases=num_total,
        temporal_cases=guard_total,
        cases=tuple(results),
    )
