"""
Leyline fount icons on the main map.

The minimap/all-map icon renderer already lets MAGATSUKA and MIMAN icons
through the fog-of-war test. Add E_MINIMAP_POI_TYPE_RYUKETSU to that check so
leyline founts are drawn through unexplored fog on the all-map.

The table rows keep ShowFar = 0, so the minimap keeps its normal local range:
a fount only appears there when it is close. No data pak is needed.
"""

from __future__ import annotations

import struct

from gameplay_patches import Asm, _jmp_site, _place, off, va

# UMinimapManager icon renderer, POIType test:
#   movzx ecx, byte ptr [rbx]      ; m_Param.m_POIType
#   sub   cl, 4
#   test  cl, 0F7h                 ; MAGATSUKA (4) or MIMAN (12)
#   je    <visible>
# The 11 bytes are replaced with a jump to a cave that also matches RYUKETSU.
POI_VISIBLE_SITE = 0x140BD3C87
POI_VISIBLE_ORIG = bytes.fromhex("0fb60b80e904f6c1f7745b")
POI_CONTINUE = 0x140BD3C92
POI_VISIBLE = 0x140BD3CED
RYUKETSU_POI_TYPE = 5


def patch_leylines(data: bytearray, cave_off: int, cave_end: int) -> int | None:
    """Add RYUKETSU to the renderer's fog bypass.

    Returns the next free cave offset, or None when the code does not match.
    """
    site = off(POI_VISIBLE_SITE)
    if data[site : site + len(POI_VISIBLE_ORIG)] != POI_VISIBLE_ORIG:
        return None

    a = Asm(va(cave_off))
    a.raw("0F B6 0B")  # movzx ecx, byte ptr [rbx]
    a.raw(f"80 F9 {RYUKETSU_POI_TYPE:02X}")  # cmp cl, RYUKETSU
    a.je(POI_VISIBLE)  # je visible
    a.raw("80 E9 04")  # sub cl, 4
    a.raw("F6 C1 F7")  # test cl, 0F7h
    a.je(POI_VISIBLE)  # je visible
    a.jmp(POI_CONTINUE)  # jmp continue
    code = a.build()

    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, code)
    _jmp_site(data, POI_VISIBLE_SITE, dest, len(POI_VISIBLE_ORIG))
    return cave_off


def site_jump_target(data: bytes) -> int | None:
    """Target VA of the installed site jump, or None if not patched."""
    site = off(POI_VISIBLE_SITE)
    if data[site] != 0xE9:
        return None
    return POI_VISIBLE_SITE + 5 + struct.unpack_from("<i", data, site + 1)[0]
