from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from multisite_crawler.mock_server import MockCrawlerServer


def test_local_server_reproduces_success_etag_and_faults() -> None:
    with MockCrawlerServer() as server:
        with urlopen(server.url) as response:  # noqa: S310
            assert response.status == 200
            etag = response.headers["ETag"]
        request = Request(server.url, headers={"If-None-Match": etag})
        try:
            urlopen(request)  # noqa: S310
        except HTTPError as error:
            assert error.code == 304
        server.state.mode = "429"
        try:
            urlopen(server.url)  # noqa: S310
        except HTTPError as error:
            assert error.code == 429
            assert error.headers["Retry-After"] == "7"
