"""Strict, site-neutral execution contract for source adapters."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from multisite_crawler.hashing import fingerprint_business_data


class AdapterRunError(RuntimeError):
    """Base failure for a named adapter operation."""


class AdapterContractError(AdapterRunError):
    """Raised when an adapter returns a value outside the shared contract."""


class FetchError(AdapterRunError):
    """Raised when fetching a source response fails."""


class ParseError(AdapterRunError):
    """Raised when a source response cannot be parsed into raw items."""


class NormalizationError(AdapterContractError):
    """Raised when raw source data cannot become a valid crawl item."""


@dataclass(frozen=True)
class FetchResult:
    """Raw source response and optional HTTP validators."""

    body: bytes
    etag: str | None = None
    last_modified: str | None = None


class CrawlItem(BaseModel):
    """Validated, source-neutral business data ready for persistence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    external_id: str = Field(min_length=1)
    data: dict[str, Any]

    @field_validator("external_id")
    @classmethod
    def reject_blank_external_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("external_id must not be blank")
        return value


@dataclass(frozen=True)
class AdapterResult:
    """A completed adapter collection with response metadata."""

    response: FetchResult
    items: tuple[CrawlItem, ...]
    raw_response_hash: str


class BaseAdapter(ABC):
    """Each website implements only this source-specific contract."""

    @abstractmethod
    def fetch(self) -> FetchResult:
        """Fetch the source response without persisting it."""

    @abstractmethod
    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        """Parse a raw response into source-shaped item mappings."""

    @abstractmethod
    def normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        """Map a source-shaped item into shared business data."""

    @abstractmethod
    def fingerprint(self, item: CrawlItem) -> str:
        """Return the canonical business fingerprint for one item."""


class AdapterRunner:
    """Run and validate a source adapter without touching storage."""

    def __init__(self, adapter: BaseAdapter) -> None:
        self._adapter = adapter

    def run(self) -> AdapterResult:
        response = self._fetch()
        raw_items = self._parse(response)
        items = tuple(self._normalize(raw_item) for raw_item in raw_items)
        return AdapterResult(
            response=response,
            items=items,
            raw_response_hash=hashlib.sha256(response.body).hexdigest(),
        )

    def _fetch(self) -> FetchResult:
        try:
            response = self._adapter.fetch()
        except AdapterRunError:
            raise
        except Exception as error:
            raise FetchError("Adapter fetch failed.") from error
        if not isinstance(response, FetchResult):
            raise AdapterContractError("fetch must return FetchResult.")
        return response

    def _parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        try:
            raw_items = self._adapter.parse(response)
        except AdapterRunError:
            raise
        except Exception as error:
            raise ParseError("Adapter parse failed.") from error
        if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
            raise AdapterContractError("parse must return a sequence of mappings.")
        if not all(isinstance(item, Mapping) for item in raw_items):
            raise AdapterContractError("parse must return only mappings.")
        return raw_items

    def _normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        try:
            item = self._adapter.normalize(raw_item)
        except ValidationError as error:
            fields = ", ".join(
                ".".join(str(part) for part in item_error["loc"])
                for item_error in error.errors()
            )
            raise NormalizationError(
                f"normalize returned invalid CrawlItem data: {fields}."
            ) from error
        except AdapterRunError:
            raise
        except Exception as error:
            raise NormalizationError("Adapter normalize failed.") from error
        if not isinstance(item, CrawlItem):
            raise AdapterContractError("normalize must return CrawlItem.")
        try:
            expected = fingerprint_business_data(item.data)
        except ValueError as error:
            raise AdapterContractError(
                "CrawlItem data must be JSON-compatible."
            ) from error
        try:
            actual = self._adapter.fingerprint(item)
        except Exception as error:
            raise AdapterContractError("Adapter fingerprint failed.") from error
        if actual != expected:
            raise AdapterContractError("Adapter fingerprint must be canonical.")
        return item
