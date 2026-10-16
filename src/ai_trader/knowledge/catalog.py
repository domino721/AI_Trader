"""Verify local source manifests without networking, parsing, or executing source text."""

import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from ai_trader.knowledge.models import Catalog, Document, Purpose


def load_catalog(path: Path) -> Catalog:
    return Catalog.model_validate_json(path.read_bytes())


def verify_content(document: Document, root: Path) -> None:
    root = root.resolve()
    relative = Path(document.content_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("content path must stay relative to source root")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("content path escapes source root")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != document.content_sha256:
        raise ValueError("source content checksum mismatch")
    text = body.decode("utf-8")
    for location in document.locations:
        if text.count(location.marker) != 1:
            raise ValueError(f"citation marker missing or ambiguous: {location.location_id}")


def check_catalog(catalog: Catalog, root: Path, decision_time: datetime, purpose: Purpose) -> dict:
    decision_time = TypeAdapter(AwareDatetime).validate_python(decision_time)
    purpose = TypeAdapter(Purpose).validate_python(purpose)
    rows = []
    for document in catalog.documents:
        reasons = []
        if document.rights.status != "approved" or purpose not in document.rights.allowed_uses:
            reasons.append("usage_not_permitted")
        if document.available_at > decision_time:
            reasons.append("unavailable_at_decision")
        # Each version is checked separately; a future correction never hides past evidence.
        if any(
            newer.supersedes == document.version_id and newer.available_at <= decision_time
            for newer in catalog.documents
        ):
            reasons.append("superseded_at_decision")
        try:
            verify_content(document, root)
        except (OSError, ValueError, UnicodeError):
            # Never echo source paths, source text or attacker-controlled exception messages.
            reasons.append("content_verification_failed")
        rows.append(
            {
                "document_id": document.document_id,
                "version_id": document.version_id,
                "available_at": document.available_at.isoformat(),
                "eligible": not reasons,
                "reasons": reasons,
            }
        )
    return {
        "status": "passed" if all(row["eligible"] for row in rows) else "blocked",
        "purpose": purpose,
        "decision_time": decision_time.isoformat(),
        "documents": rows,
        "historical_backtest_approved": False,
        "trading_approved": False,
    }
