"""Site-specific adapter contracts and their site-neutral runner."""

from multisite_crawler.adapters.base import (
    AdapterContractError,
    AdapterResult,
    AdapterRunError,
    AdapterRunner,
    BaseAdapter,
    CrawlItem,
    FetchError,
    FetchResult,
    NormalizationError,
    ParseError,
)

__all__ = [
    "AdapterContractError",
    "AdapterResult",
    "AdapterRunError",
    "AdapterRunner",
    "BaseAdapter",
    "CrawlItem",
    "FetchError",
    "FetchResult",
    "NormalizationError",
    "ParseError",
]
