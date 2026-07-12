"""Transactional, site-neutral record persistence and change detection."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from multisite_crawler.adapters.base import AdapterResult
from multisite_crawler.database import beijing_now
from multisite_crawler.hashing import fingerprint_business_data
from multisite_crawler.models import ChangeEvent, Record, SourceFetchState

INACTIVE_AFTER_SUCCESSFUL_ABSENCES = 3


class RecordRepository:
    """Persist complete adapter collections under one database transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_collection(self, source_id: UUID, result: AdapterResult) -> None:
        """Apply a successful complete collection and reconcile missing records."""
        now = beijing_now()
        observed_ids: set[str] = set()
        for item in result.items:
            observed_ids.add(item.external_id)
            self._lock_record_key(source_id, item.external_id)
            fingerprint = fingerprint_business_data(item.data)
            record = self._session.scalar(
                select(Record)
                .where(
                    Record.source_id == source_id,
                    Record.external_id == item.external_id,
                )
                .with_for_update()
            )
            if record is None:
                record = Record(
                    source_id=source_id,
                    external_id=item.external_id,
                    payload=item.data,
                    content_hash=fingerprint,
                    last_seen_at=now,
                    missing_count=0,
                )
                self._session.add(record)
                self._session.flush()
                self._event(record.id, "created", item.data)
            else:
                changed = record.content_hash != fingerprint
                record.payload = item.data
                record.last_seen_at = now
                record.missing_count = 0
                record.is_active = True
                if changed:
                    record.content_hash = fingerprint
                    self._event(record.id, "updated", item.data)
        self._update_fetch_state(source_id, result, now)
        self._reconcile_missing(source_id, observed_ids)

    def _update_fetch_state(
        self, source_id: UUID, result: AdapterResult, now: object
    ) -> None:
        state = self._session.scalar(
            select(SourceFetchState)
            .where(SourceFetchState.source_id == source_id)
            .with_for_update()
        )
        if state is None:
            state = SourceFetchState(source_id=source_id)
            self._session.add(state)
        state.etag = result.response.etag
        state.last_modified = result.response.last_modified
        state.raw_response_hash = result.raw_response_hash
        state.updated_at = now  # type: ignore[assignment]

    def _lock_record_key(self, source_id: UUID, external_id: str) -> None:
        """Serialize concurrent first inserts for one source-owned business key."""
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{source_id}:{external_id}"},
        )

    def _reconcile_missing(self, source_id: UUID, observed_ids: set[str]) -> None:
        records = self._session.scalars(
            select(Record)
            .where(Record.source_id == source_id, Record.is_active.is_(True))
            .with_for_update()
        )
        for record in records:
            if record.external_id in observed_ids:
                continue
            record.missing_count += 1
            if record.missing_count >= INACTIVE_AFTER_SUCCESSFUL_ABSENCES:
                record.is_active = False
                self._event(record.id, "inactive", record.payload)

    def _event(
        self, record_id: UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        self._session.add(
            ChangeEvent(record_id=record_id, event_type=event_type, payload=payload)
        )
