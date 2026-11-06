"""Tests for the central verification/pak manifest."""

from __future__ import annotations

import patch_manifest


def test_feature_paks_are_unique_and_named():
    keys = [key for key, _pak in patch_manifest.FEATURE_PAKS]
    names = [pak for _key, pak in patch_manifest.FEATURE_PAKS]
    assert len(keys) == len(set(keys))
    assert all(name.endswith(".pak") for name in names)


def test_static_sites_cover_every_feature():
    sites = patch_manifest.static_sites(bytearray(0x1800))
    for feature in patch_manifest.STATIC_FEATURES:
        assert feature in sites
        assert sites[feature]
        assert all(length > 0 for _offset, length, _original in sites[feature])
