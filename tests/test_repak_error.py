# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-License-Identifier: Apache-2.0

"""Change-scoped tests for repak's user-facing error message."""

from __future__ import annotations

import patch_smtvv_freeplay as ps


def test_oodle_error_is_actionable():
    message = ps._repak_error_message("Oodle loader error: ureq error Io(...)")
    assert "Oodle runtime" in message
    assert "firewall" in message
    assert "offline" in message


def test_other_errors_pass_through():
    assert ps._repak_error_message("bad pak") == "bad pak"
    assert ps._repak_error_message("") == "unknown error"
