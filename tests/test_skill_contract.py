from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_adapters import FakeAdapter

from multisite_crawler.adapters.base import AdapterRunner, FetchResult, ParseError
from multisite_crawler.adapters.demo_api import DemoApiAdapter
from multisite_crawler.mock_server import MockCrawlerServer

ROOT = Path(__file__).parents[1]
ADAPTER_SKILL = ROOT / ".agents/skills/crawler-adapter/SKILL.md"
REPAIR_SKILL = ROOT / ".agents/skills/crawler-repair/SKILL.md"
NORMAL_FIXTURE = ROOT / "tests/fixtures/demo_api_normal.json"


def test_adapter_skill_documents_the_repository_adapter_contract() -> None:
    skill = ADAPTER_SKILL.read_text(encoding="utf-8")

    for required_text in (
        "## Required Inputs",
        "official API",
        "## Fixture Procedure",
        "## Implementation Procedure",
        "BaseAdapter",
        "## Test Matrix",
        "## Monitoring And Safety",
        "## Final Report",
        "CAPTCHA",
        "Do not commit production keys",
        "src/multisite_crawler/adapters/demo_api.py::DemoApiAdapter",
        "tests/test_adapters.py::FakeAdapter",
    ):
        assert required_text in skill


def test_adapter_skill_validation_examples_run_without_a_real_website() -> None:
    with MockCrawlerServer() as server:
        server.state.items = [{"id": "skill-demo", "score": 1}]
        demo_result = AdapterRunner(DemoApiAdapter(server.url)).run()

    fake_result = AdapterRunner(FakeAdapter()).run()

    assert demo_result.items[0].external_id == "skill-demo"
    assert fake_result.items[0].external_id == "match-1"


def test_repair_skill_requires_a_test_first_safe_repair_workflow() -> None:
    skill = REPAIR_SKILL.read_text(encoding="utf-8")

    for required_text in (
        "## Required Evidence",
        "Network or transient service failure",
        "Access or session failure",
        "Page or response structure change",
        "Add a regression test and run it before changing parser code",
        "Do not change unrelated adapters",
        "## Repair Report",
        "Never bypass CAPTCHA",
    ):
        assert required_text in skill


def test_repair_validation_fixture_fails_before_the_approved_parser_input() -> None:
    adapter = DemoApiAdapter("http://127.0.0.1/not-used")
    broken_response = FetchResult(body=json.dumps({"results": []}).encode("utf-8"))
    normal_response = FetchResult(body=NORMAL_FIXTURE.read_bytes())

    with pytest.raises(ParseError, match="items document"):
        adapter.parse(broken_response)

    parsed = adapter.parse(normal_response)

    assert parsed[0]["id"] == "one"
