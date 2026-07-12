"""Adapter for the repository's controlled local demo API."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from multisite_crawler.adapters.base import (
    BaseAdapter,
    CrawlItem,
    FetchError,
    FetchResult,
    ParseError,
)
from multisite_crawler.hashing import fingerprint_business_data


class DemoApiAdapter(BaseAdapter):
    """Collect the `items` array served by `MockCrawlerServer` only."""

    def __init__(self, url: str, timeout_seconds: float = 2) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds

    def fetch(self) -> FetchResult:
        try:
            with urlopen(self._url, timeout=self._timeout_seconds) as response:  # noqa: S310
                return FetchResult(response.read(), etag=response.headers.get("ETag"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise FetchError("demo_api request failed") from error

    def parse(self, response: FetchResult) -> Sequence[Mapping[str, Any]]:
        try:
            document = json.loads(response.body)
            items = document["items"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParseError(
                "demo_api response is not a valid items document"
            ) from error
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ParseError("demo_api items must be a list of objects")
        return items

    def normalize(self, raw_item: Mapping[str, Any]) -> CrawlItem:
        identifier = raw_item.get("id")
        if not isinstance(identifier, str):
            raise ParseError("demo_api item is missing string id")
        return CrawlItem(external_id=identifier, data=dict(raw_item))

    def fingerprint(self, item: CrawlItem) -> str:
        return fingerprint_business_data(item.data)
