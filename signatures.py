"""Signature helpers for auditing patch sites and future relocation.

Each site is identified by a short window of its own bytes. If a game update
moves a site but keeps the surrounding code, the window can locate it again;
the audit reports which sites are already unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MARGIN = 16


@dataclass(frozen=True)
class SiteAudit:
    offset: int
    signature_length: int
    count: int
    unique: bool


def window(
    data: bytes | bytearray, offset: int, length: int, margin: int = DEFAULT_MARGIN
) -> bytes:
    start = max(0, offset - margin)
    end = min(len(data), offset + length + margin)
    return bytes(data[start:end])


def count_occurrences(
    data: bytes | bytearray, needle: bytes, limit: int = 4
) -> list[int]:
    positions: list[int] = []
    start = 0
    while len(positions) < limit:
        position = data.find(needle, start)
        if position < 0:
            break
        positions.append(position)
        start = position + 1
    return positions


def audit_site(
    data: bytes | bytearray, offset: int, length: int, margin: int = DEFAULT_MARGIN
) -> SiteAudit:
    signature = window(data, offset, length, margin)
    start = max(0, offset - margin)
    positions = count_occurrences(data, signature)
    return SiteAudit(
        offset=offset,
        signature_length=len(signature),
        count=len(positions),
        unique=positions == [start],
    )


def audit(
    data: bytes | bytearray,
    sites: dict[str, list[tuple[int, int, bytes]]],
    margin: int = DEFAULT_MARGIN,
) -> dict[str, list[SiteAudit]]:
    return {
        feature: [
            audit_site(data, offset, length, margin) for offset, length, _ in entries
        ]
        for feature, entries in sites.items()
    }


def locate(
    data: bytes | bytearray, offset: int, length: int, margin: int = DEFAULT_MARGIN
) -> int | None:
    """The unique start of a site's signature, or None if ambiguous/missing."""
    signature = window(data, offset, length, margin)
    positions = count_occurrences(data, signature)
    start = max(0, offset - margin)
    if positions == [start]:
        return start
    return None


def resolve(data: bytes | bytearray, known_offset: int, original: bytes) -> int | None:
    """Known offset when unchanged, otherwise its unique byte match."""
    if bytes(data[known_offset : known_offset + len(original)]) == original:
        return known_offset
    positions = count_occurrences(data, original, limit=2)
    if len(positions) == 1:
        return positions[0]
    return None


def summarise(report: dict[str, list[SiteAudit]]) -> tuple[int, int]:
    """(unique sites, total sites)."""
    entries = [entry for group in report.values() for entry in group]
    return sum(1 for entry in entries if entry.unique), len(entries)
