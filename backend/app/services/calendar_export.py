from __future__ import annotations

from datetime import datetime, timezone

from ..contact_models import Interview
from ..models import JobTrack


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def _escape(value: str) -> str:
    # RFC 5545 TEXT escaping also removes raw CR/LF so user input cannot inject
    # new properties or a second VEVENT.
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    return text


def _fold(line: str, limit: int = 75) -> list[str]:
    """Fold a content line at at most 75 UTF-8 octets, continuation prefixed by one space."""
    chunks: list[str] = []
    current = ""
    current_bytes = 0
    for char in line:
        encoded = char.encode("utf-8")
        budget = limit if not chunks else limit - 1
        if current and current_bytes + len(encoded) > budget:
            chunks.append(current)
            current = char
            current_bytes = len(encoded)
        else:
            current += char
            current_bytes += len(encoded)
    if current or not chunks:
        chunks.append(current)
    return [chunks[0], *[f" {part}" for part in chunks[1:]]]


def build_interview_ics(interview: Interview, track: JobTrack) -> bytes:
    summary_bits = [interview.round_label or "Interview"]
    if track.company:
        summary_bits.append(track.company)
    if track.title:
        summary_bits.append(track.title)
    summary = " — ".join(summary_bits)

    raw_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//JobGrid//Interview Calendar Event//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:jobgrid-interview-{interview.id}@jobgrid.local",
        f"SEQUENCE:{max(interview.version - 1, 0)}",
        f"DTSTAMP:{_stamp(interview.updated_at or interview.created_at or datetime.utcnow())}",
        f"DTSTART:{_stamp(interview.starts_at)}",
        f"DTEND:{_stamp(interview.ends_at)}",
        f"SUMMARY:{_escape(summary)}",
        f"STATUS:{'CANCELLED' if interview.status == 'cancelled' else 'CONFIRMED'}",
    ]
    if interview.location:
        raw_lines.append(f"LOCATION:{_escape(interview.location)}")
    if interview.meeting_url:
        raw_lines.append(f"URL:{_escape(interview.meeting_url)}")
    description = f"Interview type: {interview.kind}. Display timezone: {interview.timezone}."
    raw_lines.append(f"DESCRIPTION:{_escape(description)}")
    raw_lines.extend(["END:VEVENT", "END:VCALENDAR"])

    folded: list[str] = []
    for line in raw_lines:
        folded.extend(_fold(line))
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
