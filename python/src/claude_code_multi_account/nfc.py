"""Unicode 16.0 NFC with bundled tables, so results do not depend on the runtime's Unicode version."""

from __future__ import annotations

from .nfc_tables import CCC, COMP, DECOMP

_S_BASE, _L_BASE, _V_BASE, _T_BASE = 0xAC00, 0x1100, 0x1161, 0x11A7
_L_COUNT, _V_COUNT, _T_COUNT = 19, 21, 28
_N_COUNT = _V_COUNT * _T_COUNT
_S_COUNT = _L_COUNT * _N_COUNT


def _decompose(cp: int, out: list[int]) -> None:
    if _S_BASE <= cp < _S_BASE + _S_COUNT:
        s = cp - _S_BASE
        out.append(_L_BASE + s // _N_COUNT)
        out.append(_V_BASE + (s % _N_COUNT) // _T_COUNT)
        if s % _T_COUNT:
            out.append(_T_BASE + s % _T_COUNT)
        return
    parts = DECOMP.get(cp)
    if parts is None:
        out.append(cp)
        return
    for p in parts:
        _decompose(p, out)


def _compose_pair(a: int, b: int) -> int | None:
    if _L_BASE <= a < _L_BASE + _L_COUNT and _V_BASE <= b < _V_BASE + _V_COUNT:
        return _S_BASE + ((a - _L_BASE) * _V_COUNT + (b - _V_BASE)) * _T_COUNT
    if _S_BASE <= a < _S_BASE + _S_COUNT and (a - _S_BASE) % _T_COUNT == 0 and _T_BASE < b < _T_BASE + _T_COUNT:
        return a + (b - _T_BASE)
    return COMP.get((a, b))


def nfc(text: str) -> str:
    """Unicode 16.0 Normalization Form C."""
    if text.isascii():
        return text
    d: list[int] = []
    for ch in text:
        _decompose(ord(ch), d)
    i = 0
    while i < len(d):  # canonical ordering of each run of non-starters
        if CCC.get(d[i], 0) == 0:
            i += 1
            continue
        j = i
        while j < len(d) and CCC.get(d[j], 0) != 0:
            j += 1
        d[i:j] = sorted(d[i:j], key=lambda c: CCC[c])
        i = j
    out: list[int] = []
    starter = -1
    last = 0
    for cp in d:
        c = CCC.get(cp, 0)
        if starter >= 0 and not (len(out) - 1 != starter and last >= c):
            p = _compose_pair(out[starter], cp)
            if p is not None:
                out[starter] = p
                continue
        if c == 0:
            starter = len(out)
        last = c
        out.append(cp)
    return "".join(map(chr, out))
