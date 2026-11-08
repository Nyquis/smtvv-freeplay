# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-FileCopyrightText: 2026 the countlessbats/smtvv-freeplay authors
# SPDX-License-Identifier: MIT AND Apache-2.0
# Modified by Nyquis from the upstream MIT project; see LICENSING.md.

"""
Gameplay patches for the Freeplay patcher: battle consumable refill and
multi-jump with air control. Each builder writes its code into the shared
CC cave and returns the next free cave offset, or None if the expected bytes
were not found (the patch is then skipped).
"""

from __future__ import annotations

import struct

# Generic PE, emitter and cave helpers now live in code_caves. Re-exported
# here temporarily so existing importers keep working during the migration.
from code_caves import (
    IMAGE_BASE,
    RDATA_RAW,
    RDATA_VA,
    SLACK_SECTIONS,
    Asm,
    _jmp_site,
    _place,
    _range_has_reference,
    off,
    put_code,
    set_cave_references,
    set_image_layout,
    slack_caves,
    va,
)

__all__ = [
    "IMAGE_BASE",
    "RDATA_RAW",
    "RDATA_VA",
    "SLACK_SECTIONS",
    "Asm",
    "_jmp_site",
    "_place",
    "_range_has_reference",
    "off",
    "put_code",
    "set_cave_references",
    "set_image_layout",
    "slack_caves",
    "va",
]


# ---------------------------------------------------------------------------
# Battle consumable refill
# ---------------------------------------------------------------------------
# BattleMainWorkBase::SetNextStep exec thunk (a 5-byte jump into the
# protected body). After the original runs, if the battle is entering
# E_BTL_STEP_PRE (3) -- the first step of every battle -- every
# battle-usable item the player has ever obtained is topped up to its carry
# limit. The other registered copy of
# this thunk (0x140C27BC0) must stay untouched: redirecting it makes the
# game exit during startup.
SETNEXTSTEP_THUNKS = [0x140C2C2D0]
SETNEXTSTEP_ORIG = bytes.fromhex("e93b9ec307")
BTL_NEXTSTEP_OFF = 0x262  # m_NextStep
BTL_STEP_PRE = 3
BTL_STEP_READY = 2  # E_BTL_STEP_READY .. E_BTL_STEP_START_EVENT run once per
BTL_STEP_START_EVENT = 5  # battle, before the first turn
BTL_STEP_END_EVENT = 24  # E_BTL_STEP_END_EVENT .. FINISH_WAIT close a battle
BTL_STEP_FINISH_WAIT = 31  # the battle's last step

ITEM_GET = 0x140ACE9A0  # ItemGet(id, count)  (adds)
ITEM_GET_MAX = 0x140ACF220  # ItemGetMaxNum(id) -> int
ITEM_GET_NUM = 0x140ACF4F0  # ItemGetNum(id) -> int
ITEM_IS_GOTTEN = 0x140ACF6F0  # ItemIsGotten(id) -> bool
ITEM_IS_USEBATTLE = 0x140ACF7C0  # ItemIsUseBattle(id) -> bool
ITEM_GET_ORIG = bytes.fromhex("e9bb7d8c06")
ITEM_GET_MAX_ORIG = bytes.fromhex("e93b7c8d06")
ITEM_GET_NUM_ORIG = bytes.fromhex("e9cbba8d06")
ITEM_IS_GOTTEN_ORIG = bytes.fromhex("e9fbb98e06")
REFILL_ID_MAX = 135  # use items are 1..135


DEFER_SETNEXTSTEP = False
DEFERRED_STEPS: dict[str, int] = {}
STEP_ORDER = ("refill", "stockpile", "magatsuhi", "refresh", "autosave")


def patch_setnextstep(data: bytearray, caves: list[list[int]]) -> bool:
    """Install one dispatcher for every deferred SetNextStep behaviour."""
    for t in SETNEXTSTEP_THUNKS:
        if data[off(t) : off(t) + 5] != SETNEXTSTEP_ORIG:
            return False
    for t in SETNEXTSTEP_THUNKS:
        orig = t + 5 + struct.unpack_from("<i", data, off(t) + 1)[0]

        def hook(a, orig=orig):
            a.raw("53 48 83 EC 20 48 89 CB")  # push rbx; sub rsp,20h; mov rbx,rcx
            a.call(orig)
            for key in STEP_ORDER:
                target = DEFERRED_STEPS.get(key)
                if target is None:
                    continue
                a.raw("48 89 D9")  # mov rcx, rbx
                a.call(target)
            a.raw("48 83 C4 20 5B C3")
            return a

        _jmp_site(data, t, put_code(data, caves, hook), 5)
    return True


def _refill_step(orig: int | None, call_orig: bool):
    def build(a):
        a.raw("53 56 57")  # push rbx/rsi/rdi
        a.raw("48 83 EC 20")  # sub rsp, 20h
        a.raw("48 89 CB")  # mov rbx, rcx
        if call_orig:
            a.call(orig)  # original SetNextStep
        a.raw("80 BB").raw(struct.pack("<I", BTL_NEXTSTEP_OFF).hex()).raw(
            f"{BTL_STEP_PRE:02x}"
        )
        a.jne("done")
        a.raw("BE 01 00 00 00")  # mov esi, 1
        a.label("loop")
        a.raw("89 F1").call(ITEM_IS_USEBATTLE).raw("84 C0").je("next")
        a.raw("89 F1").call(ITEM_IS_GOTTEN).raw("84 C0").je("next")
        a.raw("89 F1").call(ITEM_GET_MAX).raw("89 C7")  # edi = max
        a.raw("89 F1").call(ITEM_GET_NUM).raw("29 C7")  # edi -= num
        a.jle("next")
        a.raw("89 F1 89 FA").call(ITEM_GET)  # ItemGet(id, edi)
        a.label("next")
        a.raw("FF C6")  # inc esi
        a.raw("81 FE").raw(struct.pack("<I", REFILL_ID_MAX).hex())
        a.jle("loop")
        a.label("done")
        a.raw("48 83 C4 20 5F 5E 5B C3")
        return a

    return build


def patch_refill(data: bytearray, cave_off: int, cave_end: int) -> int | None:
    for t in SETNEXTSTEP_THUNKS:
        if data[off(t) : off(t) + 5] != SETNEXTSTEP_ORIG:
            return None
    if data[off(ITEM_IS_USEBATTLE) : off(ITEM_IS_USEBATTLE) + 5] != bytes.fromhex(
        "48895c2408"
    ):
        return None
    for fn, expected in (
        (ITEM_GET, ITEM_GET_ORIG),
        (ITEM_GET_MAX, ITEM_GET_MAX_ORIG),
        (ITEM_GET_NUM, ITEM_GET_NUM_ORIG),
        (ITEM_IS_GOTTEN, ITEM_IS_GOTTEN_ORIG),
    ):
        if data[off(fn) : off(fn) + 5] != expected:
            return None

    if DEFER_SETNEXTSTEP:
        dest = va(cave_off)
        cave_off = _place(
            data, cave_off, cave_end, _refill_step(None, False)(Asm(dest)).build()
        )
        DEFERRED_STEPS["refill"] = dest
        return cave_off

    for t in SETNEXTSTEP_THUNKS:
        orig = t + 5 + struct.unpack_from("<i", data, off(t) + 1)[0]
        dest = va(cave_off)
        cave_off = _place(
            data, cave_off, cave_end, _refill_step(orig, True)(Asm(dest)).build()
        )
        _jmp_site(data, t, dest, 5)
    return cave_off


# ---------------------------------------------------------------------------
# Full Magatsuhi: fill the player's Magatsuhi gauge as each battle starts
# ---------------------------------------------------------------------------
# A battle keeps its own Magatsuhi gauges in BattleMainWorkBase: an int
# array, one per side, the player's first (the party Uplifting gauge from the
# save data is copied in before the first step, and the array is written
# back when the battle ends). The maximum is BPL_BattleCommon:
# GetUpliftingGaugeMax, a constant 100.
#
# The player's gauge is filled on the opening steps (READY .. START_EVENT).
#
# Two modes:
#   battle (default) fills at the start of every battle, including each Boss
#     Rush or chain encounter, which reuses the same BattleMainWorkBase. The
#     game copies the party gauge over the battle gauge during a chain
#     hand-off and the meter only redraws on the first action, so the gauge is
#     full from the start of the round while the meter catches up one action
#     later.
#   chain fills only for the first battle of a chain. Rounds reuse the same
#     battle actor and gauge array, so that pair identifies the chain; a new
#     battle (a new actor, normally with a new array) fills again.
BTL_GAUGES_OFF = 0x540  # TArray<int32> {data, num, max}
BTL_GAUGE_CACHE = 0x550  # player's gauge, refreshed from the array
# Scratch in the writable .xpdata page, after Stockpile's table
# (0x1549A9900..0x1549A9997). Never written to the game files.
MAGATSUHI_ACTOR = 0x1549A99A0
MAGATSUHI_ARRAY = 0x1549A99A8
UPLIFT_MAX = 100


def patch_magatsuhi(
    data: bytearray, caves: list[list[int]], chain: bool = False
) -> bool:
    for t in SETNEXTSTEP_THUNKS:
        current = data[off(t) : off(t) + 5]
        # Refill or Stockpile may already have redirected this thunk.
        if current != SETNEXTSTEP_ORIG and current[0] != 0xE9:
            return False

    def u32(v):
        return struct.pack("<I", v).hex()

    def hook(a, prev: int, chain: bool, call_prev: bool):
        a.raw("53 48 83 EC 20 48 89 CB")  # push rbx; sub rsp,20h; mov rbx,rcx
        if call_prev:
            a.call(prev)
        a.raw("0F B6 83" + u32(BTL_NEXTSTEP_OFF))  # movzx eax, byte [rbx+262h]
        a.raw(
            f"83 E8 {BTL_STEP_READY:02x} 83 F8 {BTL_STEP_START_EVENT - BTL_STEP_READY:02x}"
        )
        a.ja("done")  # opening steps only
        a.raw("48 8B 93" + u32(BTL_GAUGES_OFF))  # mov rdx, [rbx+540h]
        a.raw("48 85 D2").je("done")
        if chain:
            # A chain reuses the battle actor and its gauge array.
            a._rel("48 39 1D", MAGATSUHI_ACTOR)  # cmp [actor], rbx
            a.jne("fill")
            a._rel("48 39 15", MAGATSUHI_ARRAY)  # cmp [array], rdx
            a.je("done")
            a.label("fill")
        a.raw("83 BB" + u32(BTL_GAUGES_OFF + 8) + "00")  # cmp dword [rbx+548h], 0
        a.jle("done")
        a.raw("C7 02" + u32(UPLIFT_MAX))  # mov dword [rdx], 100
        a.raw("C7 83" + u32(BTL_GAUGE_CACHE) + u32(UPLIFT_MAX))
        if chain:
            a._rel("48 89 1D", MAGATSUHI_ACTOR)  # mov [actor], rbx
            a._rel("48 89 15", MAGATSUHI_ARRAY)  # mov [array], rdx
        a.label("done")
        a.raw("48 83 C4 20 5B C3")
        return a

    if DEFER_SETNEXTSTEP:
        DEFERRED_STEPS["magatsuhi"] = put_code(
            data, caves, lambda a: hook(a, 0, chain, False)
        )
        return True

    # Chains onto whatever the thunk currently jumps to (the Battle Refill
    # or Stockpile cave when that patch is installed).
    for t in SETNEXTSTEP_THUNKS:
        prev = t + 5 + struct.unpack_from("<i", data, off(t) + 1)[0]
        _jmp_site(
            data,
            t,
            put_code(data, caves, lambda a, prev=prev: hook(a, prev, chain, True)),
            5,
        )
    return True


# ---------------------------------------------------------------------------
# Party Refresh: restore the party's HP/MP on every battle step
# ---------------------------------------------------------------------------
def patch_party_refresh(
    data: bytearray, caves: list[list[int]], party_cure_va: int
) -> int:
    """Build and place the post-battle refresh body; return its entry VA."""

    def build(a):
        a.raw("53 48 83 EC 20 48 89 CB")  # push rbx; sub rsp,20h; mov rbx,rcx
        a.raw("0F B6 83" + struct.pack("<I", BTL_NEXTSTEP_OFF).hex())
        a.raw("83 F8 %02x" % BTL_STEP_FINISH_WAIT)
        a.jne("done")
        a.call(party_cure_va)
        a.label("done")
        a.raw("48 83 C4 20 5B C3")
        return a

    return put_code(data, caves, build)


# ---------------------------------------------------------------------------
# Hold-to-ascend and air control (PlayerMovementComponent)
# ---------------------------------------------------------------------------
PM_ON_GROUND = 0x1C8  # nonzero while grounded
PM_JUMPING = 0x250  # jump in progress
PM_TAKEOFF = 0x251  # take-off done (rising phase active)
PM_JUMP_TIME = 0x254  # seconds since take-off
PM_AIR_TIME = 0x24C

JUMP_VCALL_SITE = 0x140A6869C  # Jump(): call [rax+570h] (grounded check)
JUMP_VCALL_ORIG = bytes.fromhex("ff907005000084c074")
AIRSPEED_SITE = 0x140A6BC00  # airborne max speed: movss xmm0,[rcx+160h]
AIRSPEED_ORIG = bytes.fromhex("f30f108160010000")
INTERP_SITE = 0x140A6A985  # movss xmm0,[rdi+1BCh] (InputInterpSpeed)
INTERP_ORIG = bytes.fromhex("f30f1087bc010000")
TURN_SITE = 0x140A6ADEA  # mulss xmm0,[rdi+16Ch] (rotation rate)
TURN_ORIG = bytes.fromhex("f30f59876c010000")

ARC_SITE = 0x140A6C8C6  # rising arc: movss xmm3,[rdi+254h]
ARC_ORIG = bytes.fromhex("f30f109f54020000")
# This site is reached by JMP, not CALL. The cave assumes the surrounding
# function has RSP 0 mod 16 before its 7 pushes + sub rsp,0A8h. That holds on
# the current build; a future function-layout change needs this rechecked.

# Rising speed is velocityJump + 2*0.5*gravityJump*t (1550 - 4000*t by
# default). While jump is held the arc time is clamped here, giving a steady
# climb of about 1070 units/s.
HOLD_ARC_TIME = 0.12

IAT_GET_FOREGROUND_WINDOW = 0x1549AF7A8
IAT_GET_WINDOW_THREAD_PID = 0x1549AF878
IAT_GET_CURRENT_PID = 0x1549AEBD0
IAT_GET_ASYNC_KEY_STATE = 0x1549AF748
IAT_XINPUT_GET_STATE = 0x1549AFDF0  # xinput1_3 ordinal 2
IAT_SLOTS = {
    "CreateThread": "IAT_CREATE_THREAD",
    "Sleep": "IAT_SLEEP",
    "PostMessageW": "IAT_POST_MESSAGE",
    "GetForegroundWindow": "IAT_GET_FOREGROUND_WINDOW",
    "GetWindowThreadProcessId": "IAT_GET_WINDOW_THREAD_PID",
    "GetCurrentProcessId": "IAT_GET_CURRENT_PID",
    "GetAsyncKeyState": "IAT_GET_ASYNC_KEY_STATE",
    "XInputGetState": "IAT_XINPUT_GET_STATE",
}


def set_iat_slots(slots: dict[str, int]) -> None:
    """Point the hook constants at the import table's IAT slots."""
    module = globals()
    for name, attribute in IAT_SLOTS.items():
        module[attribute] = slots.get(name, 0)


def iat_missing(*names: str) -> list[str]:
    missing = []
    for name in names:
        attribute = IAT_SLOTS[name]
        if not globals()[attribute]:
            missing.append(name)
    return missing


VK_SPACE = 0x20
XINPUT_A_OR_B = 0x3000

AIR_SPEED_MUL = 1.5
AIR_INTERP_MUL = 8.0
AIR_TURN_MUL = 8.0


JUMP_SITES = (
    (JUMP_VCALL_SITE, JUMP_VCALL_ORIG),
    (AIRSPEED_SITE, AIRSPEED_ORIG),
    (INTERP_SITE, INTERP_ORIG),
    (TURN_SITE, TURN_ORIG),
    (ARC_SITE, ARC_ORIG),
)


def patch_jump(data: bytearray, cave_off: int, cave_end: int) -> int | None:
    if iat_missing(
        "GetForegroundWindow",
        "GetWindowThreadProcessId",
        "GetCurrentProcessId",
        "GetAsyncKeyState",
        "XInputGetState",
    ):
        return None
    import signatures

    site_va: dict[int, int] = {}
    for site, orig in JUMP_SITES:
        offset = signatures.resolve(data, off(site), orig)
        if offset is None:
            return None
        site_va[site] = va(offset)

    def u32(v):
        return struct.pack("<I", v).hex()

    # Mid-air Jump(): start rising from the current height.
    a = Asm(va(cave_off))
    a.raw("48 83 EC 28 FF 90 70 05 00 00 48 83 C4 28")  # original grounded check
    a.raw("84 C0").jne("ret")
    a.raw("80 BB" + u32(PM_ON_GROUND) + "00").jne("fail")
    for flag in (0x241, 0x242, 0x243):  # bEnableJump*
        a.raw("80 BB" + u32(flag) + "00").je("fail")
    a.raw("C6 83" + u32(PM_JUMPING) + "01")
    a.raw("C6 83" + u32(PM_TAKEOFF) + "01")
    a.raw("C7 83" + u32(PM_JUMP_TIME) + struct.pack("<f", HOLD_ARC_TIME).hex())
    a.raw("C7 83" + u32(PM_AIR_TIME) + "00000000")
    a.raw("48 8B 83 B0000000")  # mov rax,[rbx+B0h]
    a.raw("F3 0F 10 80 D8010000")  # movss xmm0,[rax+1D8h]
    for o in (0x258, 0x25C, 0x260):  # jump base height
        a.raw("F3 0F 11 83" + u32(o))
    a.label("fail")
    a.raw("31 C0")
    a.label("ret")
    a.raw("C3")
    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, a.build())
    _jmp_site(data, site_va[JUMP_VCALL_SITE], dest, 6, opcode=0xE8)

    # Rising arc tick: while jump (Space, or pad A/B) is held in the focused
    # game window, keep the arc time at HOLD_ARC_TIME so the climb continues.
    a = Asm(va(cave_off))
    a.raw("50 51 52 4150 4151 4152 4153")  # save volatiles
    a.raw("48 81 EC A8000000")
    for i in range(6):  # movdqu [rsp+40h+i*16], xmmi
        a.raw(f"F3 0F 7F {0x84 | (i << 3):02X} 24" + u32(0x40 + 16 * i))
    a._rel("FF15", IAT_GET_FOREGROUND_WINDOW)
    a.raw("48 85 C0").je("restore")
    a.raw("48 89 C1 48 8D 54 24 30")._rel("FF15", IAT_GET_WINDOW_THREAD_PID)
    a._rel("FF15", IAT_GET_CURRENT_PID)
    a.raw("3B 44 24 30").jne("restore")
    a.raw("B9" + u32(VK_SPACE))._rel("FF15", IAT_GET_ASYNC_KEY_STATE)
    a.raw("66 A9 0080").jne("held")
    a.raw("31 C9 48 8D 54 24 20")._rel("FF15", IAT_XINPUT_GET_STATE)
    a.raw("85 C0").jne("restore")
    a.raw("0F B7 44 24 24")  # wButtons
    a.raw("A9" + u32(XINPUT_A_OR_B)).je("restore")
    a.label("held")
    a.raw("F3 0F 10 87" + u32(PM_JUMP_TIME))
    a.rip("0F 2F 05", "t")  # comiss xmm0, T
    a._rel("0F86", "restore")  # t <= T: keep
    a.rip("F3 0F 10 05", "t")
    a.raw("F3 0F 11 87" + u32(PM_JUMP_TIME))
    a.raw("C7 87" + u32(PM_AIR_TIME) + "00000000")
    a.label("restore")
    for i in range(6):
        a.raw(f"F3 0F 6F {0x84 | (i << 3):02X} 24" + u32(0x40 + 16 * i))
    a.raw("48 81 C4 A8000000")
    a.raw("415B 415A 4159 4158 5A 59 58")
    a.raw(ARC_ORIG.hex())
    a.jmp(site_va[ARC_SITE] + 8)
    a.f32("t", HOLD_ARC_TIME)
    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, a.build())
    _jmp_site(data, site_va[ARC_SITE], dest, 8)

    # Airborne max speed x1.5 (this branch only runs off the ground).
    a = Asm(va(cave_off))
    a.raw(AIRSPEED_ORIG.hex())
    a.rip("F3 0F 59 05", "k")
    a.jmp(site_va[AIRSPEED_SITE] + 8)
    a.f32("k", AIR_SPEED_MUL)
    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, a.build())
    _jmp_site(data, site_va[AIRSPEED_SITE], dest, 8)

    # Input direction follows the stick much faster in the air.
    a = Asm(va(cave_off))
    a.raw(INTERP_ORIG.hex())
    a.raw("80 BF" + u32(PM_ON_GROUND) + "00").jne("back")
    a.rip("F3 0F 59 05", "k")
    a.label("back").jmp(site_va[INTERP_SITE] + 8)
    a.f32("k", AIR_INTERP_MUL)
    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, a.build())
    _jmp_site(data, site_va[INTERP_SITE], dest, 8)

    # Turn rate: undo the airborne rotation damping.
    a = Asm(va(cave_off))
    a.raw(TURN_ORIG.hex())
    a.raw("80 BF" + u32(PM_ON_GROUND) + "00").jne("back")
    a.rip("F3 0F 59 05", "k")
    a.label("back").jmp(site_va[TURN_SITE] + 8)
    a.f32("k", AIR_TURN_MUL)
    dest = va(cave_off)
    cave_off = _place(data, cave_off, cave_end, a.build())
    _jmp_site(data, site_va[TURN_SITE], dest, 8)
    return cave_off


# ---------------------------------------------------------------------------
# Title refocus: with the intro skipped, the title menu comes up with the
# controller reported as disconnected until the window is deactivated and
# reactivated. The first time the title menu ticks, a short-lived thread
# posts the deactivate/activate messages a tab-out and tab-in would send.
# ---------------------------------------------------------------------------
TITLE_TICK_IMPL = 0x140B8A000  # EnableCountUpNoInputTime(): movzx eax,[flag]; ret
TITLE_TICK_ORIG = bytes.fromhex("0fb60521e34b03c3")
TITLE_TICK_FLAG = 0x144048328  # the byte the original returns
REFOCUS_DONE = 0x1549A9800  # spare zeroed byte in a writable section page
IAT_CREATE_THREAD = 0x1549AEAC0
IAT_SLEEP = 0x1549AF088
IAT_POST_MESSAGE = 0x1549AF918
WM_ACTIVATE = 0x0006
WM_ACTIVATEAPP = 0x001C
REFOCUS_DELAY_MS = 600
REFOCUS_GAP_MS = 250


def patch_refocus(data: bytearray, caves: list[list[int]]) -> int | None:
    if iat_missing(
        "CreateThread",
        "Sleep",
        "PostMessageW",
        "GetForegroundWindow",
        "GetWindowThreadProcessId",
        "GetCurrentProcessId",
    ):
        return None
    import signatures

    site = signatures.resolve(data, off(TITLE_TICK_IMPL), TITLE_TICK_ORIG)
    if site is None:
        return None
    site_va = va(site)

    def u32(v):
        return struct.pack("<I", v).hex()

    def post_code(a, msg, wparam):
        a.raw("48 89 D9 BA" + u32(msg) + "41 B8" + u32(wparam) + "45 31 C9")
        a._rel("FF15", IAT_POST_MESSAGE)

    def build_thread(a):
        a.raw("53 48 83 EC 30")
        a.raw("B9" + u32(REFOCUS_DELAY_MS))._rel("FF15", IAT_SLEEP)
        a._rel("FF15", IAT_GET_FOREGROUND_WINDOW)
        a.raw("48 89 C3 48 85 C0").je("done")
        a.raw("48 89 C1 48 8D 54 24 28")._rel("FF15", IAT_GET_WINDOW_THREAD_PID)
        a._rel("FF15", IAT_GET_CURRENT_PID)
        a.raw("3B 44 24 28").jne("done")
        post_code(a, WM_ACTIVATE, 0)
        post_code(a, WM_ACTIVATEAPP, 0)
        a.raw("B9" + u32(REFOCUS_GAP_MS))._rel("FF15", IAT_SLEEP)
        post_code(a, WM_ACTIVATEAPP, 1)
        post_code(a, WM_ACTIVATE, 1)
        a.label("done")
        a.raw("31 C0 48 83 C4 30 5B C3")
        return a

    thread_va = put_code(data, caves, build_thread)

    def build_hook(a):
        a._rel("8A 05", REFOCUS_DONE).raw("84 C0").jne("orig")
        a.raw("B0 01")._rel("88 05", REFOCUS_DONE)
        a.raw("48 83 EC 38 31 C9 31 D2")
        a._rel("4C 8D 05", thread_va)
        a.raw("45 31 C9 48 C7 44 24 20 00 00 00 00 48 C7 44 24 28 00 00 00 00")
        a._rel("FF15", IAT_CREATE_THREAD)
        a.raw("48 83 C4 38")
        a.label("orig")
        a._rel("0F B6 05", TITLE_TICK_FLAG).raw("C3")
        return a

    dest = put_code(data, caves, build_hook)
    _jmp_site(data, site_va, dest, 8)
    return dest
