from __future__ import annotations

from pathlib import Path

import pytest

from multisite_crawler.browser_artifacts import BrowserArtifactWriter


def test_artifact_writer_rejects_full_page_html(tmp_path: Path) -> None:
    writer = BrowserArtifactWriter(tmp_path)

    with pytest.raises(ValueError, match="safe fragment"):
        writer.write_failure(source_id="demo", safe_html=None, screenshot=None)


def test_artifact_writer_removes_secret_like_attributes(tmp_path: Path) -> None:
    artifact = BrowserArtifactWriter(tmp_path).write_failure(
        source_id="demo",
        safe_html=(
            '<table><input value="secret"><tr><td token="abc">ok</td></tr></table>'
        ),
        screenshot=None,
    )

    html = artifact.html_path.read_text(encoding="utf-8")
    assert "secret" not in html
    assert "token=" not in html
    assert "<input" not in html
    assert "<table>" in html


def test_artifact_writer_rejects_invalid_source_ids(tmp_path: Path) -> None:
    writer = BrowserArtifactWriter(tmp_path)

    with pytest.raises(ValueError, match="source_id"):
        writer.write_failure(
            source_id="demo-site",
            safe_html="<table><tr><td>ok</td></tr></table>",
            screenshot=None,
        )


def test_artifact_writer_does_not_persist_screenshots(tmp_path: Path) -> None:
    artifact = BrowserArtifactWriter(tmp_path).write_failure(
        source_id="demo",
        safe_html="<table><tr><td>ok</td></tr></table>",
        screenshot=b"fake-image",
    )

    assert artifact.screenshot_path is None


def test_artifact_writer_rejects_trailing_non_table_content(tmp_path: Path) -> None:
    writer = BrowserArtifactWriter(tmp_path)

    with pytest.raises(ValueError, match="single <table> root"):
        writer.write_failure(
            source_id="demo",
            safe_html="<table><tr><td>ok</td></tr></table><html></html>",
            screenshot=None,
        )


@pytest.mark.parametrize(
    "safe_html",
    [
        "<!--comment--><table><tr><td>ok</td></tr></table>",
        "<table><tr><td>ok</td></tr></table><!--comment-->",
        "<!DOCTYPE html><table><tr><td>ok</td></tr></table>",
        "<table><tr><td>ok</td></tr></table><!DOCTYPE html>",
    ],
)
def test_artifact_writer_rejects_comment_or_declaration_outside_table_root(
    tmp_path: Path,
    safe_html: str,
) -> None:
    writer = BrowserArtifactWriter(tmp_path)

    with pytest.raises(ValueError, match="single <table> root"):
        writer.write_failure(
            source_id="demo",
            safe_html=safe_html,
            screenshot=None,
        )
