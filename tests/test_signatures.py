# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Tests for the signature helpers."""

from __future__ import annotations

import signatures


def test_window_clamps_at_the_edges():
    data = b"0123456789"
    assert signatures.window(data, 0, 2, margin=4) == b"012345"
    assert signatures.window(data, 8, 2, margin=4) == b"456789"
    assert signatures.window(data, 4, 2, margin=2) == b"234567"


def test_count_occurrences_stops_at_the_limit():
    assert signatures.count_occurrences(b"aaaaa", b"aa", limit=3) == [0, 1, 2]


def test_audit_marks_a_unique_site():
    data = bytearray(b"..UNIQUE.." + b"-" * 12)
    result = signatures.audit_site(data, 2, 6, margin=2)
    assert result.unique is True
    assert result.count == 1


def test_audit_marks_a_repeated_site():
    data = bytearray(b"..DUP.." + b"-" * 4 + b"..DUP..")
    result = signatures.audit_site(data, 2, 3, margin=2)
    assert result.unique is False
    assert result.count == 2


def test_summarise_counts_unique_and_total():
    report = {
        "a": [signatures.SiteAudit(0, 10, 1, True)],
        "b": [
            signatures.SiteAudit(1, 10, 2, False),
            signatures.SiteAudit(2, 10, 1, True),
        ],
    }
    assert signatures.summarise(report) == (2, 3)


def test_locate_returns_a_unique_start():
    data = bytearray(b"..UNIQUE.." + b"-" * 12)
    assert signatures.locate(data, 2, 6, margin=2) == 0


def test_locate_rejects_an_ambiguous_signature():
    data = bytearray(b"..DUP.." + b"-" * 4 + b"..DUP..")
    assert signatures.locate(data, 2, 3, margin=2) is None


def test_resolve_keeps_a_matching_site():
    data = bytearray(b"..UNIQUE.." + b"-" * 8)
    assert signatures.resolve(data, 2, b"UNIQUE") == 2


def test_resolve_relocates_a_unique_site():
    data = bytearray(b"x" * 32 + b"UNIQUE" + b"y" * 32)
    assert signatures.resolve(data, 0, b"UNIQUE") == 32


def test_resolve_rejects_an_ambiguous_site():
    data = bytearray(b"UNIQUE" + b"-" * 4 + b"UNIQUE")
    assert signatures.resolve(data, 100, b"UNIQUE") is None
