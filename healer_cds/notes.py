"""Raid note generation (MRT / Liquid / Northern Sky compatible {time:} syntax)."""
from __future__ import annotations

from collections import defaultdict

from .analysis import CDCluster, fmt_time
from .models import OurComp


def assign_names(ours: OurComp, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """spec -> display name(s) for the note lines."""
    names: dict[str, list[str]] = defaultdict(list)
    for h in ours.healers:
        names[h.spec_key].append(h.name)
    out = {spec: "/".join(n) for spec, n in names.items()}
    for spec, name in (overrides or {}).items():
        out[spec] = name
    return out


def _line_time(c: CDCluster, use_phases: bool) -> str:
    if use_phases and c.phase is not None:
        return f"{{time:{fmt_time(c.median)},p{c.phase}}}"
    return f"{{time:{fmt_time(c.abs_median)}}}"


def build_note(clusters: list[CDCluster], ours: OurComp, boss: str, use_phases: bool,
               include_minor: bool = False, overrides: dict[str, str] | None = None) -> str:
    """One line per timing, sorted by absolute time, merged when several CDs land together."""
    names = assign_names(ours, overrides)
    rows = [c for c in clusters if c.tier == "major" or (include_minor and c.tier != "major")]
    # merge clusters within 3s into one line
    if use_phases:
        rows.sort(key=lambda c: (c.phase if c.phase is not None else 0, c.median))
    else:
        rows.sort(key=lambda c: c.abs_median)
    lines: list[list[CDCluster]] = []
    for c in rows:
        prev = lines[-1][-1] if lines else None
        close = prev is not None and (
            abs(c.median - prev.median) <= 3 and c.phase == prev.phase if use_phases
            else abs(c.abs_median - prev.abs_median) <= 3)
        if close:
            lines[-1].append(c)
        else:
            lines.append([c])
    out = [f"{{star}} {boss} healer CDs {{star}}"]
    for group in lines:
        head = _line_time(group[0], use_phases)
        parts = [f"{names.get(c.spec_key, c.spec_key)} {{spell:{c.ability_id}}}" for c in group]
        out.append(f"{head} " + "  ".join(parts))
    return "\n".join(out)


def build_plan_text(clusters: list[CDCluster], ours: OurComp, use_phases: bool) -> str:
    """Human readable plan with confidence, for the healing channel."""
    names = assign_names(ours)
    out = []
    for c in sorted(clusters, key=lambda c: c.abs_median):
        when = f"P{c.phase} {fmt_time(c.median)}" if (use_phases and c.phase is not None) else fmt_time(c.abs_median)
        conf = f"{c.support}/{c.total_kills} kills, +/-{int(c.spread)}s"
        tag = "" if c.tier == "major" else f" [{c.tier}]"
        out.append(f"{when:>12}  {names.get(c.spec_key, c.spec_key):<16} {c.ability}{tag}  ({conf})")
    return "\n".join(out)


def build_nsrt(clusters: list[CDCluster], healer_name: str, spec: str, boss: str, encounter_id: int,
               difficulty: str, use_phases: bool, include_minor: bool = False) -> str:
    """Northern Sky Raid Tools 'Dynamic Timer' personal note for one healer.

    Format:
        EncounterID:3429;Difficulty:Heroic;Name:The Coiled Altar;
        ph:1;time:64.3;tag:Chubbycake;spellid:391528;
    time is seconds since the phase started. Without usable phase data everything goes under ph:1
    with time since pull.
    """
    rows = [c for c in clusters if c.spec_key == spec and c.tier != "discovered"
            and (c.tier == "major" or include_minor)]
    if use_phases:
        rows.sort(key=lambda c: (c.phase if c.phase is not None else 1, c.median))
    else:
        rows.sort(key=lambda c: c.abs_median)
    out = [f"EncounterID:{encounter_id};Difficulty:{difficulty.capitalize()};Name:{boss};"]
    for c in rows:
        ph = c.phase if (use_phases and c.phase is not None) else 1
        t = c.median if (use_phases and c.phase is not None) else c.abs_median
        out.append(f"ph:{ph};time:{t:.1f};tag:{healer_name};spellid:{c.ability_id};")
    return "\n".join(out)
