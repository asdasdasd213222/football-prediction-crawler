from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from multisite_crawler.adapters.base import (
    AdapterContractError,
    AdapterRunner,
    BaseAdapter,
    CrawlItem,
    FetchError,
    FetchResult,
    ParseError,
)
from multisite_crawler.hashing import fingerprint_business_data


class FakeAdapter(BaseAdapter):
    def fetch(self) -> FetchResult:
        return FetchResult(body=b'{"items":[{"id":"match-1","score":1}]}')

    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        assert response.body
        return ({"id": "match-1", "score": 1},)

    def normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        return CrawlItem(
            external_id=str(raw_item["id"]), data={"score": raw_item["score"]}
        )

    def fingerprint(self, item: CrawlItem) -> str:
        return hashlib.sha256(b'{"score":1}').hexdigest()


class InvalidAdapter(FakeAdapter):
    def normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        return CrawlItem(external_id="", data={"score": raw_item["score"]})


class EmptyAdapter(FakeAdapter):
    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        return ()


class MismatchedFingerprintAdapter(FakeAdapter):
    def fingerprint(self, item: CrawlItem) -> str:
        return "not-a-fingerprint"


class WhitespaceIdentifierAdapter(FakeAdapter):
    def normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        return CrawlItem(external_id=" ", data={"score": raw_item["score"]})


class MalformedParseAdapter(FakeAdapter):
    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        return (1,)  # type: ignore[return-value]


class FailingFetchAdapter(FakeAdapter):
    def fetch(self) -> FetchResult:
        raise OSError("source unavailable")


class FailingParseAdapter(FakeAdapter):
    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        raise ValueError("malformed payload")


def test_runner_returns_validated_fake_adapter_items() -> None:
    result = AdapterRunner(FakeAdapter()).run()

    assert [item.external_id for item in result.items] == ["match-1"]
    assert (
        result.raw_response_hash
        == hashlib.sha256(b'{"items":[{"id":"match-1","score":1}]}').hexdigest()
    )


def test_runner_rejects_blank_external_id_before_storage() -> None:
    with pytest.raises(AdapterContractError, match="external_id"):
        AdapterRunner(InvalidAdapter()).run()


def test_runner_allows_a_successful_empty_collection() -> None:
    assert AdapterRunner(EmptyAdapter()).run().items == ()


def test_runner_rejects_a_noncanonical_adapter_fingerprint() -> None:
    with pytest.raises(AdapterContractError, match="fingerprint"):
        AdapterRunner(MismatchedFingerprintAdapter()).run()


def test_runner_rejects_whitespace_external_id_before_storage() -> None:
    with pytest.raises(AdapterContractError, match="external_id"):
        AdapterRunner(WhitespaceIdentifierAdapter()).run()


def test_runner_rejects_non_mapping_parse_values() -> None:
    with pytest.raises(AdapterContractError, match="mappings"):
        AdapterRunner(MalformedParseAdapter()).run()


def test_runner_wraps_fetch_failure_with_explicit_error_type() -> None:
    with pytest.raises(FetchError, match="fetch") as error:
        AdapterRunner(FailingFetchAdapter()).run()

    assert isinstance(error.value.__cause__, OSError)


def test_runner_wraps_parse_failure_with_explicit_error_type() -> None:
    with pytest.raises(ParseError, match="parse") as error:
        AdapterRunner(FailingParseAdapter()).run()

    assert isinstance(error.value.__cause__, ValueError)


def test_canonical_business_hash_ignores_mapping_key_order() -> None:
    assert fingerprint_business_data(
        {"home": 1, "away": 0}
    ) == fingerprint_business_data({"away": 0, "home": 1})


def test_canonical_business_hash_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        fingerprint_business_data({"value": object()})
