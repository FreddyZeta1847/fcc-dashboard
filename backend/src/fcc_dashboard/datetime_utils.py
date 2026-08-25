"""
Timestamp parsing and UTC normalization for FCC Dashboard.

FCC writes log timestamps as ISO-8601 with a UTC offset (e.g.
"2026-07-16 13:55:49.563956+02:00"). This module parses that format,
normalizes any aware datetime to this project's canonical storage format
(UTC, millisecond precision, "Z" suffix — e.g. "2026-08-24T14:30:00.123Z"),
and provides the current instant in that same format.

Parsing fails loudly (raises ValueError) on malformed input — it never
guesses or silently substitutes the current time. Callers that need a
fallback-on-failure policy (e.g. the log collector, Phase 2) implement
that themselves by catching the exception; this module's contract stops
at "parse correctly, or raise clearly."
"""

from datetime import datetime, timezone


def parse_fcc_timestamp(raw: str) -> datetime:
    """Parse FCC's log timestamp format into an aware datetime.

    Raises ValueError if `raw` is not a valid ISO-8601 timestamp.
    """
    return datetime.fromisoformat(raw)


def to_utc_iso8601(dt: datetime) -> str:
    """Normalize an aware datetime to this project's canonical UTC storage format.

    Format: "YYYY-MM-DDTHH:MM:SS.mmmZ" (millisecond precision, "Z" suffix).
    Raises ValueError if `dt` is naive (no timezone info) — every timestamp
    this module handles must already be aware.
    """
    if dt.tzinfo is None:
        raise ValueError("to_utc_iso8601 requires an aware datetime")
    utc_dt = dt.astimezone(timezone.utc)
    millis = utc_dt.microsecond // 1000
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{millis:03d}Z"


def now_utc_iso8601() -> str:
    """Current instant, UTC, in this project's canonical storage format.

    Used for `ingested_at` and as the fallback `occurred_at` value when a
    log line's own timestamp can't be parsed (the collector's policy,
    Phase 2 — this function just supplies "now" in the right format).
    """
    return to_utc_iso8601(datetime.now(timezone.utc))
