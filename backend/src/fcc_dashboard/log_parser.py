"""
Parser for a single line of FCC's `server.log`.

FCC (the local LLM gateway/proxy this dashboard watches) writes one JSON
object per line to its log file. Most lines are irrelevant to the
dashboard — startup messages, unrelated trace events, HTTP access logs.
Per BACKEND--collector.md, the collector only cares about three trace
events that together describe a request's lifecycle:

  - "provider.request.sent"              — a request left FCC for a provider
  - "provider.response.completed"        — a provider responded successfully
  - "provider.response.transport_error"  — the request failed in transit

`parse_log_line` is the single gate for that filter: given one raw line,
it returns the parsed dict only if the line is valid JSON, is a JSON
object, and its "event" field is one of the three above — otherwise it
returns None. The collector loop (Task 4) tails the log file line by
line and feeds each line through this function unconditionally, so it
must never raise: a blank line, truncated JSON from a torn write, or any
other garbage must degrade to None rather than crash the collector.
"""

import json

_RELEVANT_EVENTS = frozenset({
    "provider.request.sent",
    "provider.response.completed",
    "provider.response.transport_error",
})


def parse_log_line(raw_line: str) -> dict | None:
    """Parse one raw FCC log line, keeping only the three trace events.

    Returns the parsed JSON object as a dict if the line is valid JSON,
    the result is a JSON object (not a list/string/number/etc.), and its
    "event" field is one of the three trace events the collector cares
    about. Returns None for everything else: blank/whitespace-only
    lines, invalid JSON, non-object JSON, and JSON objects with a
    missing or irrelevant "event" field.

    Never raises — any exception during parsing (malformed JSON,
    unexpected input shape) is treated as "not a relevant line".
    """
    if not raw_line or not raw_line.strip():
        return None

    try:
        parsed = json.loads(raw_line)
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
        return None

    if not isinstance(parsed, dict):
        return None

    event = parsed.get("event")
    # `event` can be any JSON value (list, dict, number, ...) if the log
    # line is malformed — guard the type before the set membership check,
    # since testing membership on an unhashable value (a list or dict)
    # raises TypeError instead of returning False.
    if not isinstance(event, str) or event not in _RELEVANT_EVENTS:
        return None

    return parsed
