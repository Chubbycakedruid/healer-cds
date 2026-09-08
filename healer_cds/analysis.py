"""Comp matching and cooldown clustering."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .models import Kill, OurComp

SPEC_TO_CLASS = {
    "Restoration Druid": ("Druid", "Restoration"),
    "Discipline Priest": ("Priest", "Discipline"),
    "Holy Priest": ("Priest", "Holy"),
    "Holy Paladin": ("Paladin", "Holy"),
    "Mistweaver Monk": ("Monk", "Mistweaver"),
    "Restoration Shaman": ("Shaman", "Restoration"),
    "Preservation Evoker": ("Evoker", "Preservation"),
}


def spec_key(class_name: str, spec_name: str) -> str:
    return f"{spec_name} {class_name}"


# ----------------------------------------------------------------- matching
def jaccard_multiset(a: list[str], b: list[str]) -> float:
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0.0


def score_kill(kill: Kill, ours: OurComp, target_duration: float,
               w_comp: float, w_dur: float) -> tuple[float, str]:
    comp = jaccard_multiset(kill.healer_specs, ours.healer_specs)
    # duration closeness: 1.0 at the target, 0 at +/- 40% away
    if target_duration > 0:
        dur = max(0.0, 1.0 - abs(kill.duration - target_duration) / (0.4 * target_duration))
    else:
        dur = 0.5
    score = w_comp * comp + w_dur * dur
    shared = Counter(kill.healer_specs) & Counter(ours.healer_specs)
    missing = Counter(ours.healer_specs) - Counter(kill.healer_specs)
    extra = Counter(kill.healer_specs) - Counter(ours.healer_specs)
    notes = f"{sum(shared.values())}/{len(ours.healer_specs)} healer specs match"
    if missing:
        notes += "; they lack " + ", ".join(f"{k}" for k in missing.elements())
    if extra:
        notes += "; they bring " + ", ".join(f"{k}" for k in extra.elements())
    notes += f"; kill {fmt_time(kill.duration)}"
    return score, notes


# --------------------------------------------------------------- clustering
@dataclass
class CDCluster:
    spec_key: str
    ability: str
    ability_id: int
    tier: str
    phase: int | None            # None when using absolute time
    median: float                # seconds (phase-relative if phase set)
    spread: float                # interquartile-ish spread in seconds
    support: int                 # number of kills contributing
    total_kills: int
    abs_median: float            # absolute seconds from pull (for the timeline)
    samples: list[float] = field(default_factory=list)
    players: list[str] = field(default_factory=list)   # who cast it, across kills
    cd: float = 60.0                                   # cooldown length in seconds

    @property
    def support_pct(self) -> float:
        return self.support / self.total_kills if self.total_kills else 0.0


def _cluster_times(points: list[tuple], gap: float) -> list[list[tuple]]:
    """points: (time, kill_code, abs_time, player). Greedy 1-D clustering on time with a max gap."""
    pts = sorted(points, key=lambda p: p[0])
    clusters: list[list[tuple]] = []
    for p in pts:
        if clusters and p[0] - clusters[-1][-1][0] <= gap:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


def phases_are_usable(kills: list[Kill]) -> bool:
    """True if a clear majority of kills carry phase transitions with consistent ids."""
    with_phases = [k for k in kills if k.phases]
    if len(with_phases) < max(2, int(0.6 * len(kills))):
        return False
    # a boss that loops its phases (Entombed Sentinels: P1, P2, P1, P2 ...) cannot be described as
    # "P1 0:38": that would merge every P1. Such bosses get timers from pull instead.
    if any(len(set(pid for pid, _ in k.phases)) != len(k.phases) for k in with_phases):
        return False
    id_sets = Counter(tuple(sorted(pid for pid, _ in k.phases)) for k in with_phases)
    most_common, n = id_sets.most_common(1)[0]
    return n >= 0.6 * len(with_phases)


def cluster_cooldowns(kills: list[Kill], cooldowns: dict[str, list[dict]],
                      gap: float, min_support: float, use_phases: bool,
                      discover_unlisted: bool = True) -> list[CDCluster]:
    """Group each (spec, ability) cast across kills into recurring timings."""
    ignore = {n.lower() for n in (cooldowns.get("discovery") or {}).get("ignore", []) if isinstance(n, str)}
    listed: dict[str, dict[str, dict]] = {
        spec: {c["name"].lower(): c for c in cds} for spec, cds in cooldowns.items() if isinstance(cds, list)
    }
    # (spec, ability) -> list of (time, kill code, abs time, player)
    buckets: dict[tuple[str, str, int | None], list] = defaultdict(list)
    meta: dict[tuple[str, str], tuple[int, str, float]] = {}
    n_kills = len(kills)
    # support is judged against the kills that actually had that spec, not all kills
    kills_with_spec: Counter = Counter()
    for k in kills:
        for spec in set(h.spec_key for h in k.healers):
            kills_with_spec[spec] += 1

    # for discovery: casts per kill per (spec, ability), and spacing between a player's casts
    per_kill_counts: dict[tuple[str, str], list[int]] = defaultdict(list)
    gaps: dict[tuple[str, str], list[float]] = defaultdict(list)

    for k in kills:
        counts: Counter = Counter()
        for c in k.casts:
            counts[(c.spec_key, c.ability)] += 1
        for key, n in counts.items():
            per_kill_counts[key].append(n)
        last_by: dict[tuple[str, str, str], float] = {}
        for c in sorted(k.casts, key=lambda c: c.t):
            lk = (c.spec_key, c.player, c.ability)
            if lk in last_by:
                gaps[(c.spec_key, c.ability)].append(c.t - last_by[lk])
            last_by[lk] = c.t
        for c in k.casts:
            if c.ability.lower() in ignore:
                continue
            cfg = listed.get(c.spec_key, {}).get(c.ability.lower())
            if cfg is None:
                # match on id as a fallback (renamed spell)
                for cand in listed.get(c.spec_key, {}).values():
                    if c.ability_id in cand.get("ids", []):
                        cfg = cand
                        break
            if cfg is None:
                if not discover_unlisted:
                    continue
                tier, cd = "discovered", 60
            else:
                tier, cd = cfg.get("tier", "major"), cfg.get("cd", 60)
            # prefer the canonical spell ID from cooldowns.toml: logs sometimes record the effect
            # ID (e.g. Tranquility shows as 157982) while in-game tools expect the cast ID (740)
            canon_id = (cfg.get("ids") or [c.ability_id])[0] if cfg else c.ability_id
            meta[(c.spec_key, c.ability)] = (canon_id, tier, cd)
            if use_phases and c.phase is not None:
                buckets[(c.spec_key, c.ability, c.phase)].append((c.t_in_phase, k.code, c.t, c.player))
            else:
                buckets[(c.spec_key, c.ability, None)].append((c.t, k.code, c.t, c.player))

    # discovery filter: an unlisted ability only counts as a "cooldown" if it is cast
    # rarely (<= 4 times per kill on average) and by most kills that have that spec
    def is_real_cd(key: tuple[str, str]) -> bool:
        _, tier, _ = meta[key]
        if tier != "discovered":
            return True
        cnts = per_kill_counts.get(key, [])
        if not cnts or statistics.mean(cnts) > 4 or len(cnts) < 0.5 * kills_with_spec.get(key[0], n_kills):
            return False
        # a real cooldown is re-cast on a cooldown-like rhythm; rotational filler is not
        g = gaps.get(key, [])
        return not g or statistics.median(g) >= 45

    # Effective cooldown from the logs: talents and set bonuses shorten cooldowns (Convoke 120 -> 60,
    # Revival with the right talent). If the kill healers repeatedly re-cast an ability sooner than
    # cooldowns.toml says, trust the logs. 10th percentile of a player's own re-cast gaps, needing
    # several samples so one odd cast (a reset, a log artefact) cannot shrink it.
    def effective_cd(key: tuple[str, str], cd: float) -> float:
        g = sorted(x for x in gaps.get(key, []) if x > 10)
        if len(g) < 5:
            return cd
        p10 = g[max(0, int(len(g) * 0.1) - 1)]
        # talents shorten cooldowns by up to about half; anything shorter is double-logged casts
        if p10 < cd * 0.4:
            return cd
        return round(p10) if p10 < cd * 0.95 else cd

    out: list[CDCluster] = []
    for (spec, ability, phase), pts in buckets.items():
        if not is_real_cd((spec, ability)):
            continue
        ability_id, tier, cd = meta[(spec, ability)]
        cd = effective_cd((spec, ability), cd)
        spec_kills = kills_with_spec.get(spec, n_kills) or n_kills
        eff_gap = max(gap, min(cd * 0.35, 45))
        for cl in _cluster_times(pts, eff_gap):
            codes = {p[1] for p in cl}
            support = len(codes)
            if support < max(2, round(min_support * spec_kills)):
                continue
            times = [p[0] for p in cl]
            abs_times = [p[2] for p in cl]
            med = statistics.median(times)
            q = statistics.quantiles(times, n=4) if len(times) >= 4 else [min(times), med, max(times)]
            spread = (q[-1] - q[0])
            players = sorted({p[3] for p in cl})
            out.append(CDCluster(spec, ability, ability_id, tier, phase, med, spread, support,
                                 spec_kills, statistics.median(abs_times), sorted(times), players, cd))
    out.sort(key=lambda c: (c.abs_median, c.spec_key))
    return out


# ------------------------------------------------------------- damage curve
def average_damage_curve(kills: list[Kill], step: float = 2.0) -> list[tuple[float, float]]:
    """Average damage-taken per second across kills on an absolute time axis."""
    if not kills:
        return []
    horizon = max(k.duration for k in kills)
    n_bins = int(horizon // step) + 1
    sums = [0.0] * n_bins
    counts = [0] * n_bins
    for k in kills:
        for t, v in k.damage:
            b = int(t // step)
            if 0 <= b < n_bins:
                sums[b] += v
                counts[b] += 1
    return [(i * step, sums[i] / counts[i] if counts[i] else 0.0) for i in range(n_bins)]


def damage_peaks(curve: list[tuple[float, float]], top: int = 12, min_sep: float = 12.0) -> list[tuple[float, float]]:
    """Local maxima of the average damage curve, biggest first, at least min_sep apart."""
    if len(curve) < 3:
        return []
    mean = sum(v for _, v in curve) / len(curve)
    cands = []
    for i in range(1, len(curve) - 1):
        v = curve[i][1]
        if v >= curve[i - 1][1] and v >= curve[i + 1][1] and v > max(curve[i - 1][1], curve[i + 1][1]) \
                and v > 1.25 * mean:
            cands.append(curve[i])
    cands.sort(key=lambda p: -p[1])
    chosen: list[tuple[float, float]] = []
    for c in cands:
        if all(abs(c[0] - o[0]) >= min_sep for o in chosen):
            chosen.append(c)
        if len(chosen) >= top:
            break
    return sorted(chosen)


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


# ------------------------------------------------------------- mechanics
def attribute_mechanics(kills: list[Kill], clusters: list[CDCluster], peaks: list[tuple[float, float]],
                        lead: float = 8.0, lag: float = 12.0) -> tuple[dict[int, str], list[str]]:
    """Name the boss ability doing the damage around each cooldown timing and each damage peak.

    Returns ({index of cluster: mechanic}, [mechanic per peak]). A mechanic is only named when it
    accounts for at least 30% of the damage taken in the window across the kills.
    """
    def top_ability(t0: float, t1: float) -> str | None:
        totals: Counter = Counter()
        for k in kills:
            for name, pts in k.damage_abilities.items():
                totals[name] += sum(v for t, v in pts if t0 <= t <= t1)
        if not totals:
            return None
        name, v = totals.most_common(1)[0]
        grand = sum(totals.values())
        return name if grand > 0 and v / grand >= 0.3 and name.lower() not in ("melee", "total") else None

    by_cluster = {}
    for i, c in enumerate(clusters):
        m = top_ability(c.abs_median - lead, c.abs_median + lag)
        if m:
            by_cluster[i] = m
    peak_names = [top_ability(t - 6, t + 6) or "" for t, _ in peaks]
    return by_cluster, peak_names


# ------------------------------------------------------------- exemplars
def exemplar_sequences(kills: list[Kill], clusters: list[CDCluster], our_specs: list[str],
                       window: float = 20.0) -> dict[str, dict]:
    """For each of our specs, the kill healer whose major-cooldown sequence best matches the consensus.

    Score = for each of their major casts, the support share of the nearest consensus timing of that
    ability (0 if none within the window), summed. Ties go to the shorter kill.
    """
    majors = [c for c in clusters if c.tier == "major"]
    by_ability: dict[tuple[str, str], list[CDCluster]] = defaultdict(list)
    for c in majors:
        by_ability[(c.spec_key, c.ability)].append(c)
    out: dict[str, dict] = {}
    for spec in set(our_specs):
        best = None
        for k in kills:
            for h in k.healers:
                if h.spec_key != spec:
                    continue
                casts = [c for c in k.casts if c.player == h.name and (c.spec_key, c.ability) in by_ability]
                if not casts:
                    continue
                score = 0.0
                for c in casts:
                    near = [cl for cl in by_ability[(c.spec_key, c.ability)] if abs(cl.abs_median - c.t) <= window]
                    if near:
                        score += max(cl.support_pct for cl in near)
                cand = (score, -k.duration, k, h, casts)
                if best is None or cand[:2] > best[:2]:
                    best = cand
        if best:
            score, _, k, h, casts = best
            out[spec] = {"player": h.name, "guild": k.guild, "region": k.region, "url": k.url,
                         "duration": k.duration, "score": round(score, 2),
                         "casts": [{"ability": c.ability, "ability_id": c.ability_id, "t": round(c.t, 1),
                                    "phase": c.phase, "t_in_phase": round(c.t_in_phase, 1) if c.t_in_phase is not None else None}
                                   for c in sorted(casts, key=lambda c: c.t)]}
    return out
