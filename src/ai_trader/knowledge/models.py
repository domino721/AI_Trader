"""Versioned source contracts, independent of any parser, index or LLM provider."""

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from ai_trader.domain import Record

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")]
Purpose = Literal["local_storage", "indexing", "model_context"]


def public_url(value: HttpUrl) -> HttpUrl:
    if value.username or value.password:
        raise ValueError("source references must not contain credentials")
    return value


SourceUrl = Annotated[HttpUrl, AfterValidator(public_url)]


class UsageRights(Record):
    status: Literal["approved", "pending", "denied"] = "pending"
    license_name: Text
    evidence_url: SourceUrl
    checked_at: AwareDatetime
    allowed_uses: tuple[Purpose, ...] = ()
    attribution: Text
    conditions: Text

    @model_validator(mode="after")
    def validate_grant(self) -> "UsageRights":
        if len(self.allowed_uses) != len(set(self.allowed_uses)):
            raise ValueError("duplicate permitted use")
        if (self.status == "approved") != bool(self.allowed_uses):
            raise ValueError("only approved rights may grant nonempty permitted uses")
        return self


class FilingIdentity(Record):
    cik: str = Field(pattern=r"^\d{10}$")
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: Text
    accepted_at: AwareDatetime
    report_date: date | None = None
    # Acceptance is not proof of actual dissemination or provider arrival time.


class CitationLocation(Record):
    location_id: Identifier
    label: Text
    # An exact UTF-8 marker in this specific file, not an invented page number.
    marker: Text


class Document(Record):
    schema_version: Literal["1.0"] = "1.0"
    document_id: Identifier
    kind: Literal["original_principle", "paper", "sec_filing"]
    source_url: SourceUrl
    retrieval_url: SourceUrl
    title: Text
    authors: tuple[Text, ...] = Field(min_length=1)
    edition: Text
    published_on: date
    first_observed_at: AwareDatetime
    retrieved_at: AwareDatetime
    # Leave unknown unless the precise public availability time is evidenced.
    public_available_at: AwareDatetime | None = None
    availability_evidence_url: SourceUrl | None = None
    content_path: Text
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["text/markdown", "text/html", "application/xml", "text/plain"]
    rights: UsageRights
    locations: tuple[CitationLocation, ...] = Field(min_length=1)
    limitations: tuple[Text, ...] = Field(min_length=1)
    supersedes: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    filing: FilingIdentity | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> "Document":
        if self.first_observed_at > self.retrieved_at:
            raise ValueError("first observation cannot follow retrieval")
        if self.published_on > self.first_observed_at.date():
            raise ValueError("publication date cannot follow first observation")
        if (self.public_available_at is None) != (self.availability_evidence_url is None):
            raise ValueError("public availability requires both timestamp and evidence")
        if self.public_available_at is not None:
            if self.public_available_at > self.first_observed_at:
                raise ValueError("public availability cannot follow first observation")
            if self.public_available_at.date() < self.published_on:
                raise ValueError("public availability cannot precede publication date")
        if (self.kind == "sec_filing") != (self.filing is not None):
            raise ValueError("only SEC filings require filing identity")
        if self.filing is not None:
            prefix = (
                f"/Archives/edgar/data/{int(self.filing.cik)}/"
                f"{self.filing.accession.replace('-', '')}/"
            )
            suffix = (self.source_url.path or "").removeprefix(prefix)
            if (
                self.source_url.scheme != "https"
                or self.source_url.host != "www.sec.gov"
                or not (self.source_url.path or "").startswith(prefix)
                or not suffix
                or "%" in suffix
                or any(part in {".", "..", ""} for part in suffix.split("/"))
                or self.source_url.query
                or self.source_url.fragment
                or self.source_url.port != 443
            ):
                raise ValueError("filing source must match canonical SEC accession directory")
            if self.retrieval_url != self.source_url:
                raise ValueError("filing receipt must refer to the same primary document URL")
            if self.filing.accepted_at > self.available_at:
                raise ValueError("filing cannot be available before acceptance")
            if self.filing.report_date and self.filing.report_date > self.published_on:
                raise ValueError("report date cannot follow publication")
        ids = [location.location_id for location in self.locations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate citation location")
        return self

    @property
    def available_at(self) -> datetime:
        # Publication dates and EDGAR acceptance alone never backdate knowledge.
        return self.public_available_at or self.first_observed_at

    @property
    def version_id(self) -> str:
        # Bind bytes, edition, rights, timestamps, correction links and locations.
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Catalog(Record):
    schema_version: Literal["1.0"] = "1.0"
    documents: tuple[Document, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_versions(self) -> "Catalog":
        versions = {document.version_id: document for document in self.documents}
        if len(versions) != len(self.documents):
            raise ValueError("duplicate document version")
        roots, successors = set(), set()
        for document in self.documents:
            if document.supersedes:
                if document.supersedes in successors:
                    raise ValueError("ambiguous correction branches")
                successors.add(document.supersedes)
                previous = versions.get(document.supersedes)
                if previous is None or previous.document_id != document.document_id:
                    raise ValueError(
                        "correction must reference an included version of same document"
                    )
                if previous.available_at >= document.available_at:
                    raise ValueError("correction must become available after its predecessor")
            else:
                if document.document_id in roots:
                    raise ValueError("multiple versions require an explicit correction chain")
                roots.add(document.document_id)
        return self


PARSER_VERSION = "plain-v1"
CHUNKER_VERSION = "fixed-char-v1"


class Chunk(Record):
    chunk_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: Identifier
    version_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["original_principle", "paper", "sec_filing"]
    title: Text
    edition: Text
    source_url: SourceUrl
    available_at: AwareDatetime
    allowed_uses: tuple[Purpose, ...] = Field(min_length=1)
    attribution: Text
    location_id: Identifier
    location_label: Text
    chunk_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    parser_version: Literal["plain-v1"] = PARSER_VERSION
    chunker_version: Literal["fixed-char-v1"] = CHUNKER_VERSION
    text: Text
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    untrusted_data_only: Literal[True] = True
    instruction_like: bool = False

    @model_validator(mode="after")
    def validate_chunk(self) -> "Chunk":
        if self.char_end <= self.char_start:
            raise ValueError("chunk end must follow start")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("chunk text checksum mismatch")
        return self


class KnowledgeSnapshot(Record):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: Literal["plain-v1"] = PARSER_VERSION
    chunker_version: Literal["fixed-char-v1"] = CHUNKER_VERSION
    documents: tuple[Document, ...] = Field(min_length=1)
    chunks: tuple[Chunk, ...] = Field(min_length=1)
    untrusted_data_only: Literal[True] = True
    historical_backtest_approved: Literal[False] = False
    trading_approved: Literal[False] = False


class SearchHit(Record):
    chunk_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: Identifier
    version_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: Text
    edition: Text
    source_url: SourceUrl
    available_at: AwareDatetime
    attribution: Text
    location_id: Identifier
    location_label: Text
    chunk_index: int = Field(ge=0)
    score: float = Field(gt=0)
    text: Text
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    untrusted_data_only: Literal[True] = True
    instruction_like: bool = False


class SearchReport(Record):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    query: Text
    decision_time: AwareDatetime
    purpose: Purpose
    eligible_documents: int = Field(ge=0)
    excluded_documents: dict[str, tuple[str, ...]]
    hits: tuple[SearchHit, ...]
    untrusted_data_only: Literal[True] = True
    historical_backtest_approved: Literal[False] = False
    trading_approved: Literal[False] = False


class EvaluationCase(Record):
    case_id: Identifier
    description: Text
    query: Text
    decision_time: AwareDatetime
    purpose: Purpose = "model_context"
    top_k: int = Field(default=3, ge=1, le=20)
    expect_empty: bool = False
    expected_document_id: Identifier | None = None
    expected_location_id: Identifier | None = None
    required_substrings: tuple[Text, ...] = ()
    expected_exclusion_reason: Text | None = None

    @model_validator(mode="after")
    def validate_expectation(self) -> "EvaluationCase":
        if self.expect_empty:
            if self.expected_document_id or self.expected_location_id or self.required_substrings:
                raise ValueError("empty-expectation case cannot require hit document or substrings")
        else:
            if not self.expected_document_id or not self.expected_location_id:
                raise ValueError(
                    "positive case requires expected_document_id and expected_location_id"
                )
        return self


class EvaluationBenchmark(Record):
    schema_version: Literal["1.0"] = "1.0"
    benchmark_id: Identifier
    catalog_path: Text
    cases: tuple[EvaluationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> "EvaluationBenchmark":
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evaluation case_id")
        return self


class CaseResult(Record):
    case_id: Identifier
    passed: bool
    top_document_id: str | None = None
    top_location_id: str | None = None
    matched_substrings: tuple[str, ...] = ()
    missing_substrings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class EvaluationReport(Record):
    schema_version: Literal["1.0"] = "1.0"
    benchmark_id: Identifier
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed", "blocked"]
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    hit_rate: float = Field(ge=0.0, le=1.0)
    citation_accuracy: float = Field(ge=0.0, le=1.0)
    numeric_accuracy: float = Field(ge=0.0, le=1.0)
    temporal_guard_accuracy: float = Field(ge=0.0, le=1.0)
    cases: tuple[CaseResult, ...]
    untrusted_data_only: Literal[True] = True
    historical_backtest_approved: Literal[False] = False
    trading_approved: Literal[False] = False
