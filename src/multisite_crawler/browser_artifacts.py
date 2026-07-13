"""Redacted browser failure artifacts for adapter-supplied safe fragments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_EVENT_ATTRIBUTE_PREFIX = "on"
_REMOVED_ATTRIBUTES = {"authorization", "cookie", "password", "token"}
_REMOVED_TAGS = {
    "button",
    "form",
    "input",
    "option",
    "script",
    "select",
    "style",
    "textarea",
}
_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link"}


@dataclass(frozen=True)
class BrowserFailureArtifact:
    """Paths for a redacted failure artifact."""

    html_path: Path
    screenshot_path: Path | None


@dataclass(frozen=True)
class RedactedPng:
    """An adapter-confirmed redacted PNG safe to persist as a failure artifact."""

    content: bytes


class BrowserArtifactWriter:
    """Persist redacted browser artifacts from adapter-supplied safe fragments."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def write_failure(
        self,
        *,
        source_id: str,
        safe_html: str | None,
        screenshot: RedactedPng | object | None,
    ) -> BrowserFailureArtifact:
        self._validate_source_id(source_id)
        fragment = self._validate_safe_html(safe_html)
        sanitized_html = _SafeFragmentSanitizer.sanitize(fragment)
        artifact_id = uuid4().hex
        html_path = self._output_dir / f"{source_id}_{artifact_id}.html"
        html_path.write_text(sanitized_html, encoding="utf-8")
        screenshot_path = self._write_redacted_png(source_id, artifact_id, screenshot)
        return BrowserFailureArtifact(
            html_path=html_path, screenshot_path=screenshot_path
        )

    def _write_redacted_png(
        self, source_id: str, artifact_id: str, screenshot: RedactedPng | object | None
    ) -> Path | None:
        if not isinstance(screenshot, RedactedPng):
            return None
        if not screenshot.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("redacted screenshot must be a PNG")
        screenshot_path = self._output_dir / f"{source_id}_{artifact_id}.png"
        screenshot_path.write_bytes(screenshot.content)
        return screenshot_path

    @staticmethod
    def _validate_source_id(source_id: str) -> None:
        if not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError("source_id must match [a-z0-9_]+")

    @staticmethod
    def _validate_safe_html(safe_html: str | None) -> str:
        if safe_html is None:
            raise ValueError("safe fragment is required")

        fragment = safe_html.strip()
        if not fragment:
            raise ValueError("safe fragment must be an adapter-supplied table fragment")

        if not _SingleTableRootValidator.is_valid(fragment):
            raise ValueError(
                "safe fragment must be an adapter-supplied single <table> root"
            )
        return fragment


class _SingleTableRootValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._root_seen = False
        self._stack: list[str] = []
        self._is_valid = True

    @classmethod
    def is_valid(cls, fragment: str) -> bool:
        validator = cls()
        validator.feed(fragment)
        validator.close()
        return validator._is_valid and validator._root_seen and not validator._stack

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        normalized_tag = tag.lower()
        if not self._stack:
            if self._root_seen or normalized_tag != "table":
                self._is_valid = False
                return
            self._root_seen = True
        if normalized_tag not in _VOID_TAGS:
            self._stack.append(normalized_tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if not self._stack or self._stack[-1] != normalized_tag:
            self._is_valid = False
            return
        self._stack.pop()

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if self._is_valid:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self._stack and data.strip():
            self._is_valid = False

    def handle_comment(self, data: str) -> None:
        del data
        if not self._stack:
            self._is_valid = False

    def handle_decl(self, decl: str) -> None:
        del decl
        if not self._stack:
            self._is_valid = False

    def unknown_decl(self, data: str) -> None:
        del data
        if not self._stack:
            self._is_valid = False

    def handle_pi(self, data: str) -> None:
        del data
        if not self._stack:
            self._is_valid = False


class _SafeFragmentSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skipped_tag_stack: list[str] = []

    @classmethod
    def sanitize(cls, fragment: str) -> str:
        sanitizer = cls()
        sanitizer.feed(fragment)
        sanitizer.close()
        return "".join(sanitizer._parts)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        if self._skipped_tag_stack:
            if normalized_tag == self._skipped_tag_stack[-1]:
                self._skipped_tag_stack.append(normalized_tag)
            return
        if normalized_tag in _REMOVED_TAGS:
            self._skipped_tag_stack.append(normalized_tag)
            return

        serialized_attrs = self._serialize_attrs(attrs)
        self._parts.append(f"<{normalized_tag}{serialized_attrs}>")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._skipped_tag_stack:
            if normalized_tag == self._skipped_tag_stack[-1]:
                self._skipped_tag_stack.pop()
            return
        if normalized_tag not in _VOID_TAGS:
            self._parts.append(f"</{normalized_tag}>")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        if self._skipped_tag_stack or normalized_tag in _REMOVED_TAGS:
            return

        serialized_attrs = self._serialize_attrs(attrs)
        self._parts.append(f"<{normalized_tag}{serialized_attrs}>")

    def handle_data(self, data: str) -> None:
        if not self._skipped_tag_stack:
            self._parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self._skipped_tag_stack:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skipped_tag_stack:
            self._parts.append(f"&#{name};")

    def _serialize_attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        kept: list[str] = []
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            if name.startswith(_EVENT_ATTRIBUTE_PREFIX) or name in _REMOVED_ATTRIBUTES:
                continue
            if raw_value is None:
                kept.append(f" {name}")
                continue
            kept.append(f' {name}="{escape(raw_value, quote=True)}"')
        return "".join(kept)
