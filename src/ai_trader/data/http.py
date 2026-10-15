import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from ai_trader.data.archive import Archive
from ai_trader.data.models import Receipt


class SourceFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SourceClient:
    ALLOWED = {"query1.finance.yahoo.com", "data.sec.gov"}

    def __init__(
        self,
        archive: Archive,
        client: httpx.Client,
        *,
        refresh: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        pinned_receipts: tuple[Receipt, ...] | None = None,
    ):
        self.archive = archive
        self.client = client
        self.refresh = refresh
        self.sleep = sleep
        self.receipts: list[Receipt] = []
        self.offline = pinned_receipts is not None
        self.pinned = {r.request_key: r for r in pinned_receipts or ()}

    def get(self, url: str, provider: str, user_agent: str) -> dict:
        parsed = httpx.URL(url)
        if parsed.scheme != "https" or parsed.host not in self.ALLOWED or parsed.userinfo:
            raise SourceFailure("unsupported_source_url")
        if self.offline:
            if pinned := self.pinned.get(self.archive.key(url)):
                return self._decode(pinned)
            raise SourceFailure("missing_pinned_receipt")
        cached = None if self.refresh else self.archive.cached(url)
        if cached is not None:
            return self._decode(cached)
        for attempt in range(3):
            # Serial requests, at most one SEC request/sec; no hidden parallel fan-out.
            self.sleep(1.0 if provider == "sec" else 0.25)
            try:
                response = self.client.get(url, headers={"User-Agent": user_agent})
            except httpx.ProxyError as error:
                self.archive.log(url, provider, "proxy_error")
                raise SourceFailure("proxy_error") from error
            except httpx.ProtocolError as error:
                self.archive.log(url, provider, "protocol_error")
                raise SourceFailure("protocol_error") from error
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                self.archive.log(url, provider, "network_error")
                if attempt == 2:
                    raise SourceFailure("network_error") from error
                self.sleep(0.5 * 2**attempt)
                continue
            self.archive.log(url, provider, f"http_{response.status_code}")
            if response.status_code == 200:
                receipt = self.archive.record(url, provider, response.content)
                return self._decode(receipt)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                delay = 0.5 * 2**attempt
                if retry_after := response.headers.get("Retry-After"):
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = (
                                parsedate_to_datetime(retry_after) - datetime.now(UTC)
                            ).total_seconds()
                        except (TypeError, ValueError):
                            raise SourceFailure("invalid_retry_after") from None
                if not 0 <= delay <= 5:
                    raise SourceFailure("retry_deferred")
                self.sleep(delay)
                continue
            raise SourceFailure(f"http_{response.status_code}")
        raise SourceFailure("attempts_exhausted")

    def _decode(self, receipt: Receipt) -> dict:
        # Failed decoding still needs a pinned raw reference in the audit record.
        self.receipts.append(receipt)
        try:
            result = json.loads(self.archive.read(receipt))
        except (ValueError, OSError) as error:
            raise SourceFailure("invalid_or_corrupt_raw_data") from error
        if not isinstance(result, dict):
            raise SourceFailure("unexpected_json_shape")
        return result
