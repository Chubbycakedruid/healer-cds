"""Boss mechanic timeline from kill logs, cooldown evidence, and the team coverage planner."""
from __future__ import annotations

import difflib
import statistics
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from .analysis import _cluster_times
from .models import Kill, OurComp

BOSS_DIR = Path(__file__).resolve().parent.parent / "bosses"
PLANNABLE = ("throughput", "sustained", "dr", "external")
WINDOW_BEFORE, WINDOW_AFTER = 8.0, 12.0


def _slug(name: str) -> str:
    return "".join(ch for ch in name.lower().replace(" ", "-") if ch.isalnum() or ch == "-")


def load_boss_file(boss_name: str) -> dict | None:
    if not BOSS_DIR.exists():
        return None
    files = {p.stem: p for p in BOSS_DIR.glob("*.toml")}
    slug = _slug(boss_name)
    hit = files.get(slug)
    if not hit:
        m = difflib.get_close_matches(slug, list(files), n=1, cutoff=0.5)
        hit = files[m[0]] if m else None
    if not hit:
        return None
    with hit.open("rb") as f:
        d = tomllib.load(f)
    d["_file"] = hit.name
    return d


def _match_mechanic(cast_name: str, mechanics: list[dict]) -> dict | None:
    low = cast_name.lower()
    for m in mechanics:
        if m["name"].lower() == low:
            return m
    for m in mechanics:
        if m["name"].lower() in low or low in m["name"].lower():
            return m
    return None


# ---------------------------------------------------------------- timeline
def mechanic_timeline(kills: list[Kill], boss: dict | None, use_phases: bool,
                      gap: float = 12.0, min_support: float = 0.3) -> tuple[list[dict], list[dict]]:
    """Cluster boss casts across kills into mechanic occurrences.

    Returns (occurrences, unlisted). Each occurrence: mechanic name, phase, t (in phase or absolute),
    abs_t, support/total, magnitude (avg damage taken per kill in the window), type/cover/weight/notes
    from the boss file. Unlisted: boss casts seen in logs that the boss file does not know, by count.
    """
    mechanics = list((boss or {}).get("mechanic", []))
    kills_with = [k for k in kills if k.boss_casts]
    n = len(kills_with)
    if not n:
        return [], []
    if not mechanics:
        # No mechanic file: every boss cast that shows up as damage taken in the logs becomes a mechanic.
        # Type and cover are left to the kill evidence (apply_evidence), weight 2 so it gets planned.
        dmg_names: Counter = Counter()
        for k in kills_with:
            for name, pts in k.damage_abilities.items():
                if name.lower() not in ("melee", "total"):
                    dmg_names[name] += sum(v for _, v in pts)
        cast_names = {name for k in kills_with for name, _ in k.boss_casts}
        for name, total in dmg_names.most_common(10):
            match = next((c for c in cast_names if c.lower() == name.lower() or name.lower() in c.lower() or c.lower() in name.lower()), None)
            if match and total > 0:
                mechanics.append({"name": match, "type": "burst", "school": "", "cover": [], "weight": 2,
                                  "notes": "From the logs only (no mechanic file): timing from the boss's casts, cover from what the kill healers used."})
        if not mechanics:
            # damage names did not line up with cast names: fall back to the boss's most regular casts
            freq: Counter = Counter()
            for k in kills_with:
                for name in {n for n, _ in k.boss_casts}:
                    freq[name] += 1
            for name, cnt in freq.most_common(8):
                if cnt >= 0.5 * n:
                    mechanics.append({"name": name, "type": "burst", "school": "", "cover": [], "weight": 1,
                                      "notes": "From the logs only: a regular boss cast. Priority and cover come from what the kill healers did around it."})
    buckets: dict[tuple[str, int | None], list] = defaultdict(list)
    unlisted: Counter = Counter()
    for k in kills_with:
        seen_unlisted = set()
        for name, t in k.boss_casts:
            m = _match_mechanic(name, mechanics)
            if m is None:
                # keep a note of what the boss casts that we have no entry for
                if name not in seen_unlisted:
                    unlisted[name] += 1
                    seen_unlisted.add(name)
                continue
            if m.get("weight", 1) <= 0:
                continue
            ph, tp = k.phase_of(t) if use_phases else (None, None)
            key = (m["name"], ph if use_phases else None)
            buckets[key].append((tp if use_phases and tp is not None else t, k.code, t, name))
    occurrences = []
    for (mname, ph), pts in buckets.items():
        m = next(x for x in mechanics if x["name"] == mname)
        for cl in _cluster_times(pts, gap):
            support = len({p[1] for p in cl})
            if support < max(2, round(min_support * n)):
                continue
            t_med = statistics.median(p[0] for p in cl)
            abs_med = statistics.median(p[2] for p in cl)
            dur = 20.0 if m.get("type") in ("dot", "absorb") else 12.0
            mags = []
            for k in kills_with:
                pts_k = k.damage_abilities.get(mname) or _fuzzy_series(k.damage_abilities, mname)
                if pts_k:
                    mags.append(sum(v for t, v in pts_k if abs_med - 2 <= t <= abs_med + dur))
                else:
                    mags.append(sum(v for t, v in k.damage if abs_med - 2 <= t <= abs_med + dur) * 0.5)
            occurrences.append({
                "mechanic": mname, "phase": ph, "t": round(t_med, 1), "abs_t": round(abs_med, 1),
                "support": support, "total": n, "magnitude": round(statistics.mean(mags)) if mags else 0,
                "type": m.get("type", "burst"), "school": m.get("school", ""), "cover": m.get("cover", ["throughput"]),
                "weight": m.get("weight", 1), "notes": m.get("notes", ""), "casts": sorted(set(p[3] for p in cl)),
            })
    occurrences.sort(key=lambda o: o["abs_t"])
    unl = [{"name": k, "kills": v} for k, v in unlisted.most_common() if v >= 2]
    return occurrences, unl


def _fuzzy_series(series: dict, name: str):
    low = name.lower()
    for k, v in series.items():
        if low in k.lower() or k.lower() in low:
            return v
    return None


# ---------------------------------------------------------------- evidence
def cooldown_evidence(kills: list[Kill], occurrences: list[dict], our_specs: list[str],
                      cooldowns: dict[str, list[dict]]) -> list[dict]:
    """For each occurrence: what the kill healing teams stacked around it.

    Kinds and stacking depth count every healer in the kill (a paladin's Aura Mastery is still 'one DR');
    ability-level evidence counts only specs we have, since that is all we can copy.
    """
    kind_of = {(spec, c["name"].lower()): c.get("kind", "throughput") for spec, lst in cooldowns.items() if isinstance(lst, list) for c in lst}
    out = []
    for o in occurrences:
        by_ability: Counter = Counter()
        by_kind: Counter = Counter()
        kills_any = 0
        counts: list[int] = []            # how many of our-spec cooldowns each kill stacked here
        combos: Counter = Counter()       # which kind-combinations they used (sorted tuple)
        for k in kills:
            hit = False
            seen = set()
            kinds_this_kill = set()
            kinds_list: list[str] = []
            for c in k.casts:
                kind = kind_of.get((c.spec_key, c.ability.lower()))
                if kind not in PLANNABLE:
                    continue
                if o["abs_t"] - WINDOW_BEFORE <= c.t <= o["abs_t"] + WINDOW_AFTER:
                    key = (c.spec_key, c.ability)
                    if key not in seen:
                        if c.spec_key in our_specs:
                            by_ability[key] += 1
                        seen.add(key)
                        kinds_list.append(kind)
                    kinds_this_kill.add(kind)
                    hit = True
            for kind in kinds_this_kill:
                by_kind[kind] += 1
            kills_any += hit
            if k.healers:
                counts.append(len(seen))
                if seen:
                    combos[tuple(sorted(kinds_list))] += 1
        typical = int(statistics.median(counts)) if counts else 0
        combo = list(combos.most_common(1)[0][0]) if combos else []
        out.append({"kills_any": kills_any, "total": len(kills),
                    "typical_count": typical, "typical_combo": combo, "max_count": max(counts) if counts else 0,
                    "by_kind": dict(by_kind),
                    "by_ability": [{"spec": s, "ability": a, "kills": v} for (s, a), v in by_ability.most_common()]})
    return out


# ------------------------------------------------------------------ planner
def apply_evidence(occurrences: list[dict], evidence: list[dict], kind_threshold: float = 0.25) -> None:
    """Let the kill logs reshape what each mechanic wants, in place.

    - cover: kinds the kill healers actually used there (in at least kind_threshold of kills) come first,
      in order of how often; the boss file's list is kept behind them as a fallback only.
    - weight: if most kills threw cooldowns at it, it is at least a 3; if almost nobody did, at most a 1.
    Each occurrence records what changed so the dashboard can say so.
    """
    for o, e in zip(occurrences, evidence):
        total = max(1, e.get("total", 1))
        used = sorted(((k, v / total) for k, v in (e.get("by_kind") or {}).items()), key=lambda x: -x[1])
        observed = [k for k, share in used if share >= kind_threshold and k in PLANNABLE]
        file_cover = [k for k in o.get("cover", []) if k in PLANNABLE]
        o["file_cover"] = file_cover
        o["file_weight"] = o.get("weight", 1)
        if observed:
            o["cover"] = observed + [k for k in file_cover if k not in observed]
        any_share = e.get("kills_any", 0) / total
        if any_share >= 0.6 and o["weight"] > 0:
            o["weight"] = max(o["weight"], 3)
        elif any_share < 0.15 and o["weight"] > 0:
            o["weight"] = min(o["weight"], 1)
        o["log_share"] = round(any_share, 2)


def plan_team(occurrences: list[dict], evidence: list[dict], ours: OurComp,
              cooldowns: dict[str, list[dict]], canon_ids: dict[tuple[str, str], int],
              leeway: float = 0.9, owned: set[tuple[str, str]] | None = None,
              cd_seen: dict[tuple[str, str], float] | None = None) -> dict:
    """Assign the team's cooldowns to mechanic occurrences.

    Priority is the mechanic's weight (from the boss file) then measured damage. A weight 3 mechanic
    gets two covers (a DR if it accepts one, plus healing), weight 2 gets one, weight 1 gets one external
    or minor. Each cooldown respects its own timer across the whole fight. Among candidates of an
    acceptable kind, the one the kill logs actually used there wins, then majors over minors.
    """
    # cooldown instances owned by our healers
    inst = []
    for h in ours.healers:
        for c in (cooldowns.get(h.spec_key) or []):
            kind = c.get("kind", "throughput")
            if kind not in PLANNABLE:
                continue
            # only plan with abilities this spec is actually seen casting (talent choices like
            # Revival vs Restoral, Yu'lon vs Chi-Ji, Wrath vs Crusader are exclusive)
            if owned is not None and (h.spec_key, c["name"]) not in owned:
                continue
            inst.append({"healer": h.name, "spec": h.spec_key, "ability": c["name"], "kind": kind,
                         # the cooldown the kill logs show (talents shorten some), else the listed one
                         "cd": float((cd_seen or {}).get((h.spec_key, c["name"]), c.get("cd", 60))), "tier": c.get("tier", "major"),
                         "ability_id": canon_ids.get((h.spec_key, c["name"]), (c.get("ids") or [0])[0]),
                         "uses": []})

    def available(i: dict, t: float) -> bool:
        return all(abs(t - u) >= i["cd"] * leeway for u in i["uses"])

    order = sorted(range(len(occurrences)), key=lambda idx: (-occurrences[idx]["weight"], -occurrences[idx]["magnitude"]))
    assignments: list[dict] = []
    for idx in order:
        o = occurrences[idx]
        ev = evidence[idx] if idx < len(evidence) else {"by_ability": [], "total": 1}
        ev_map = {(e["spec"], e["ability"]): e["kills"] / max(1, ev["total"]) for e in ev["by_ability"]}
        want = [k for k in o["cover"] if k in PLANNABLE]
        if not want or o["weight"] <= 0:
            continue
        # how many cooldowns to stack here: what the comp-matched kills typically stacked, else by weight.
        # This is the overlap control: we never put more on a mechanic than the kills did.
        typical = ev.get("typical_count", 0)
        if ev.get("kills_any", 0) / max(1, ev.get("total", 1)) >= 0.3 and typical > 0:
            slots = max(1, min(3, typical))
        else:
            slots = 2 if o["weight"] >= 3 else 1
        combo = ev.get("typical_combo") or []
        o["slots"] = slots
        picked_kinds: list[str] = []
        for _ in range(slots):
            best = None
            for i in inst:
                if i["kind"] not in want or not available(i, o["abs_t"]):
                    continue
                if i["kind"] in picked_kinds and combo.count(i["kind"]) <= picked_kinds.count(i["kind"]) and len(want) > 1:
                    continue        # only stack the same kind twice if the kills did
                if o["weight"] <= 1 and i["tier"] == "major" and i["kind"] != "external":
                    continue        # don't burn majors on weight 1 mechanics
                score = (ev_map.get((i["spec"], i["ability"]), 0.0) * 6      # what the kills pressed here dominates
                         + (1.0 if i["tier"] == "major" else 0.3)
                         + (0.6 - 0.2 * want.index(i["kind"]))                 # kinds in observed-frequency order
                         - i["cd"] / 1000.0)   # slight preference for shorter cooldowns when equal
                if best is None or score > best[0]:
                    best = (score, i)
            if best is None:
                break
            i = best[1]
            i["uses"].append(o["abs_t"])
            picked_kinds.append(i["kind"])
            assignments.append({"occ": idx, "healer": i["healer"], "spec": i["spec"], "ability": i["ability"],
                                "ability_id": i["ability_id"], "kind": i["kind"], "cd": i["cd"],
                                "evidence": round(ev_map.get((i["spec"], i["ability"]), 0.0), 2)})
    # fill pass: a major that never got used is wasted, so hang it on the heaviest mechanic that can
    # still take it (max three covers on one mechanic)
    covers = Counter(a["occ"] for a in assignments)
    filled: Counter = Counter()
    for i in inst:
        if i["uses"] or i["tier"] != "major" or i["kind"] not in ("throughput", "dr", "sustained"):
            continue
        for idx in order:
            o = occurrences[idx]
            cap = o.get("slots", 1)     # never stack more than the kills typically did
            if o["weight"] < 2 or i["kind"] not in o["cover"] or covers[idx] >= cap or filled[idx] >= 1 \
                    or not available(i, o["abs_t"]):
                continue
            i["uses"].append(o["abs_t"])
            covers[idx] += 1
            filled[idx] += 1
            assignments.append({"occ": idx, "healer": i["healer"], "spec": i["spec"], "ability": i["ability"],
                                "ability_id": i["ability_id"], "kind": i["kind"], "cd": i["cd"], "evidence": 0.0, "fill": True})
            break
    # last resort: a mechanic that wanted a specific kind and got nothing takes any healing cooldown
    covered = {a["occ"] for a in assignments}
    for idx in order:
        o = occurrences[idx]
        if o["weight"] < 2 or idx in covered:
            continue
        best = None
        for i in inst:
            if i["kind"] == "external" or (o["type"] == "absorb" and i["kind"] == "dr" and "dr" not in o["cover"]) \
                    or not available(i, o["abs_t"]):
                continue
            score = (1.5 if i["tier"] == "major" else 0.4) - i["cd"] / 1000.0
            if best is None or score > best[0]:
                best = (score, i)
        if best:
            i = best[1]
            i["uses"].append(o["abs_t"])
            covered.add(idx)
            assignments.append({"occ": idx, "healer": i["healer"], "spec": i["spec"], "ability": i["ability"],
                                "ability_id": i["ability_id"], "kind": i["kind"], "cd": i["cd"], "evidence": 0.0, "fallback": True})
    gaps = [idx for idx, o in enumerate(occurrences) if o["weight"] >= 2 and idx not in covered]
    return {"assignments": sorted(assignments, key=lambda a: occurrences[a["occ"]]["abs_t"]), "gaps": gaps,
            "unused": [{"healer": i["healer"], "ability": i["ability"], "kind": i["kind"]} for i in inst
                       if not i["uses"] and i["tier"] == "major"]}
