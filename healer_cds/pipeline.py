"""Pulls everything needed for one boss from Warcraft Logs."""
from __future__ import annotations

import difflib
from collections import Counter

from .analysis import SPEC_TO_CLASS, score_kill, spec_key
from .models import Cast, Healer, Kill, OurComp
from .wcl import DIFFICULTY, WCLClient, WCLError

HEALER_SPECS = set(SPEC_TO_CLASS)


def _fuzzy(name: str, options: list[str]) -> str | None:
    low = {o.lower(): o for o in options}
    if name.lower() in low:
        return low[name.lower()]
    # substring first ("Ula'tek" inside "Ula'tek, the ...")
    subs = [o for o in options if name.lower() in o.lower() or o.lower() in name.lower()]
    if len(subs) == 1:
        return subs[0]
    m = difflib.get_close_matches(name.lower(), list(low), n=1, cutoff=0.6)
    return low[m[0]] if m else None


def resolve_zone(client: WCLClient, raid_name: str) -> dict:
    zones = client.zones()
    names = [z["name"] for z in zones]
    hit = _fuzzy(raid_name, names)
    if not hit:
        raise WCLError(f"Could not find a raid called '{raid_name}'. Zones seen: {', '.join(names[-15:])}")
    return next(z for z in zones if z["name"] == hit)


def resolve_encounter(zone: dict, boss_name: str) -> dict:
    names = [e["name"] for e in zone["encounters"]]
    hit = _fuzzy(boss_name, names)
    if not hit:
        raise WCLError(f"No boss like '{boss_name}' in {zone['name']}. Bosses: {', '.join(names)}")
    return next(e for e in zone["encounters"] if e["name"] == hit)


# ----------------------------------------------------------- our own comp
def _healers_from_details(pd: dict) -> list[Healer]:
    out = []
    for p in pd.get("healers", []) or []:
        specs = p.get("specs") or []
        spec = max(specs, key=lambda s: s.get("count", 0))["spec"] if specs else "?"
        key = spec_key(p.get("type", "?"), spec)
        out.append(Healer(name=p.get("name", "?"), spec_key=key, actor_id=p.get("id")))
    return out


def our_comp(client: WCLClient, guild_id: int, zone_id: int, encounter_id: int,
             difficulty: int, recent_reports: int, verbose: bool = False) -> OurComp | None:
    reports = client.guild_reports(guild_id, zone_id, recent_reports)
    lineups: Counter = Counter()
    names_by_spec: dict[str, Counter] = {}
    pulls = 0
    best_pct = None
    longest = 0.0
    phases: list[tuple[int, float]] = []
    used: list[str] = []
    for rep in reports:
        fights = client.report_fights(rep["code"], encounter_id, difficulty)
        if not fights:
            continue
        used.append(rep["code"])
        for f in fights:
            pulls += 1
            dur = (f["endTime"] - f["startTime"]) / 1000
            pct = f.get("fightPercentage")
            if f.get("kill"):
                best_pct = 0.0
            elif pct is not None and (best_pct is None or pct < best_pct):
                best_pct = pct
            if dur > longest:
                longest = dur
                phases = [(p["id"], (p["startTime"] - f["startTime"]) / 1000) for p in f.get("phaseTransitions") or []]
        # comp from the last (most recent) few fights in the report
        for f in fights[-3:]:
            healers = _healers_from_details(client.player_details(rep["code"], f["id"]))
            if not healers:
                continue
            lineups[tuple(sorted(h.spec_key for h in healers))] += 1
            for h in healers:
                names_by_spec.setdefault(h.spec_key, Counter())[h.name] += 1
    if not lineups:
        return None
    lineup = lineups.most_common(1)[0][0]
    healers = []
    seen: Counter = Counter()
    for spec in lineup:
        # pick the most common name for this spec, skipping names already assigned
        for name, _ in names_by_spec[spec].most_common():
            if seen[name] == 0:
                healers.append(Healer(name=name, spec_key=spec))
                seen[name] += 1
                break
    if verbose:
        print(f"  {pulls} pulls across {len(used)} reports; healer lineup: {', '.join(lineup)}")
    return OurComp(healers=healers, pulls=pulls, best_pct=best_pct, phases=phases,
                   longest_pull=longest, source_reports=used)


# ------------------------------------------------------- candidate kills
def candidate_kills(client: WCLClient, encounter_id: int, difficulty: int, ours: OurComp,
                    per_spec: int, regions: list[str], verbose: bool = False) -> list[Kill]:
    seen: dict[tuple[str, int], Kill] = {}
    for spec in sorted(set(ours.healer_specs)):
        cls, sp = SPEC_TO_CLASS[spec]
        page, got = 1, 0
        while got < per_spec and page <= 5:
            data = client.character_rankings(encounter_id, difficulty, cls, sp, page=page)
            ranks = data.get("rankings") or []
            if not ranks:
                break
            for r in ranks:
                rep = r.get("report") or {}
                code, fid = rep.get("code"), rep.get("fightID")
                if not code or fid is None:
                    continue
                region = ((r.get("server") or {}).get("region") or "").upper()
                if regions and region not in [x.upper() for x in regions]:
                    continue
                if (code, fid) in seen:
                    continue
                seen[(code, fid)] = Kill(
                    code=code, fight_id=fid,
                    guild=(r.get("guild") or {}).get("name") or r.get("name", "?"),
                    region=region, duration=(r.get("duration") or 0) / 1000, healers=[],
                )
                got += 1
                if got >= per_spec:
                    break
            if not data.get("hasMorePages"):
                break
            page += 1
        if verbose:
            print(f"  {spec}: {got} candidate kills")
    return list(seen.values())


def enrich_and_rank(client: WCLClient, kills: list[Kill], ours: OurComp, target_duration: float,
                    w_comp: float, w_dur: float, keep: int, verbose: bool = False) -> tuple[list[Kill], float]:
    for k in kills:
        k.healers = _healers_from_details(client.player_details(k.code, k.fight_id))
    if target_duration <= 0 and kills:
        import statistics
        target_duration = statistics.median([k.duration for k in kills if k.duration > 0] or [0])
    for k in kills:
        k.score, k.match_notes = score_kill(k, ours, target_duration, w_comp, w_dur)
    kills.sort(key=lambda k: -k.score)
    chosen = kills[:keep]
    if verbose:
        for k in chosen:
            print(f"  {k.score:.2f}  {k.guild:<28} {k.match_notes}")
    return chosen, target_duration


# ------------------------------------------------------------ fight detail
def _boss_cast_list(client: WCLClient, code: str, fight: dict, npc_names: list[str], ability_names: dict,
                    encounter_name: str = "") -> list[tuple[str, float]]:
    """(ability, t) for casts by the boss NPCs. begincast+cast pairs are collapsed to the begincast.

    With a mechanic file the NPC names come from it. Without one, the boss is guessed: enemy NPCs in the
    fight whose name shares a word with the encounter name, else the first two enemy NPCs listed."""
    all_npcs = client.npc_actors(code)
    if npc_names:
        wanted = {n.lower() for n in npc_names}
        actors = [a for a in all_npcs if str(a.get("name", "")).lower() in wanted]
    else:
        in_fight = {e.get("id") for e in fight.get("enemyNPCs") or []}
        cands = [a for a in all_npcs if a.get("id") in in_fight] or all_npcs
        words = {w.lower().strip("',") for w in encounter_name.split() if len(w) > 3}
        actors = [a for a in cands if any(w in str(a.get("name", "")).lower() for w in words)]
        if not actors:
            actors = cands[:2]
    if not actors:
        return []
    ev = client.enemy_casts(code, fight, [a["id"] for a in actors])
    out: list[tuple[str, float]] = []
    last: dict[str, float] = {}
    for e in sorted(ev, key=lambda e: e["timestamp"]):
        name = ability_names.get(e.get("abilityGameID", 0)) or f"#{e.get('abilityGameID')}"
        t = (e["timestamp"] - fight["startTime"]) / 1000
        if name in last and t - last[name] < 3.0:
            continue
        last[name] = t
        out.append((name, round(t, 1)))
    return out


def load_fight_detail(client: WCLClient, kill: Kill, our_specs: list[str], verbose: bool = False,
                      npc_names: list[str] | None = None) -> None:
    fights = client.report_fights(kill.code)
    fight = next((f for f in fights if f["id"] == kill.fight_id), None)
    if not fight:
        return
    kill.duration = (fight["endTime"] - fight["startTime"]) / 1000
    kill.phases = [(p["id"], (p["startTime"] - fight["startTime"]) / 1000)
                   for p in fight.get("phaseTransitions") or []]
    md = client.master_data(kill.code)
    ability_names = {a["gameID"]: a["name"] for a in md.get("abilities") or []}

    # every healer's casts: our specs give timings and ability choice, the others still tell us how
    # many cooldowns of which kind the team stacked on each mechanic
    relevant = [h for h in kill.healers if h.actor_id is not None]
    events = client.casts(kill.code, fight, [h.actor_id for h in relevant])
    by_actor = {h.actor_id: h for h in relevant}
    for e in events:
        h = by_actor.get(e.get("sourceID"))
        if not h:
            continue
        t = (e["timestamp"] - fight["startTime"]) / 1000
        aid = e.get("abilityGameID", 0)
        c = Cast(spec_key=h.spec_key, player=h.name, ability=ability_names.get(aid, f"#{aid}"),
                 ability_id=aid, t=t)
        c.phase, c.t_in_phase = kill.phase_of(t)
        kill.casts.append(c)

    g = client.damage_taken_graph(kill.code, fight)
    kill.damage = _damage_series(g, fight)
    try:
        kill.boss_casts = _boss_cast_list(client, kill.code, fight, npc_names or [], ability_names, fight.get("name", ""))
    except Exception as e:
        if verbose:
            print(f"  (no boss casts for {kill.code}: {e})")
    try:
        ga = client.damage_taken_by_ability(kill.code, fight)
        kill.damage_abilities = _ability_series(ga, fight)
    except Exception as e:  # mechanic names are a nice-to-have, never fatal
        if verbose:
            print(f"  (no per-ability damage for {kill.code}: {e})")
    if verbose:
        print(f"  {kill.guild}: {len(kill.casts)} healer casts, {len(kill.phases)} phase transitions")


def _ability_series(graph: dict, fight: dict) -> dict[str, list[tuple[float, float]]]:
    """viewBy Ability graph -> {ability name: [(t, dtps)]}, only the abilities that matter (top 12 by total)."""
    series = [s for s in (graph.get("series") or []) if str(s.get("name", "")).lower() != "total"]
    series.sort(key=lambda s: -(s.get("total") or 0))
    out: dict[str, list[tuple[float, float]]] = {}
    for s in series[:12]:
        interval = (s.get("pointInterval") or 1000) / 1000
        start = s.get("pointStart", fight["startTime"])
        pts = []
        for i, pt in enumerate(s.get("data") or []):
            v = pt[1] if isinstance(pt, (list, tuple)) else (pt or 0)
            pts.append(((start - fight["startTime"]) / 1000 + i * interval, v / interval))
        out[str(s.get("name"))] = pts
    return out


def _damage_series(graph: dict, fight: dict) -> list[tuple[float, float]]:
    series = graph.get("series") or []
    if not series:
        return []
    total = next((s for s in series if str(s.get("name", "")).lower() == "total"), None)
    chosen = [total] if total else series
    interval = (chosen[0].get("pointInterval") or 1000) / 1000
    start = chosen[0].get("pointStart", fight["startTime"])
    n = max(len(s.get("data") or []) for s in chosen)
    out = []
    for i in range(n):
        v = 0.0
        for s in chosen:
            d = s.get("data") or []
            if i < len(d):
                pt = d[i]
                v += pt[1] if isinstance(pt, (list, tuple)) else (pt or 0)
        t = (start - fight["startTime"]) / 1000 + i * interval
        out.append((t, v / interval))   # per second
    return out


# ------------------------------------------------------------ our own pulls
def our_pull_details(client: WCLClient, guild_id: int, zone_id: int, encounter_id: int, difficulty: int,
                     recent_reports: int, n_pulls: int, verbose: bool = False,
                     npc_names: list[str] | None = None, live: bool = False) -> list[dict]:
    """Healer casts on our most recent n pulls of the boss, newest first.

    live=True re-reads the newest report's fight list instead of trusting the cache, so a report that is
    still being uploaded during the raid shows tonight's latest pulls."""
    reports = client.guild_reports(guild_id, zone_id, recent_reports)
    pulls: list[dict] = []
    for i, rep in enumerate(sorted(reports, key=lambda r: -r["startTime"])):
        fights = client.report_fights(rep["code"], encounter_id, difficulty, fresh=(live and i == 0))
        for f in sorted(fights, key=lambda f: -f["startTime"]):
            if len(pulls) >= n_pulls:
                break
            healers = _healers_from_details(client.player_details(rep["code"], f["id"]))
            md = client.master_data(rep["code"])
            names = {a["gameID"]: a["name"] for a in md.get("abilities") or []}
            events = client.casts(rep["code"], f, [h.actor_id for h in healers if h.actor_id is not None])
            by_actor = {h.actor_id: h for h in healers}
            phases = [(p["id"], (p["startTime"] - f["startTime"]) / 1000) for p in f.get("phaseTransitions") or []]
            tmp = Kill(rep["code"], f["id"], "us", "", (f["endTime"] - f["startTime"]) / 1000, healers, phases)
            casts = []
            for e in events:
                h = by_actor.get(e.get("sourceID"))
                if not h:
                    continue
                t = (e["timestamp"] - f["startTime"]) / 1000
                ph, tp = tmp.phase_of(t)
                casts.append({"player": h.name, "spec": h.spec_key, "ability": names.get(e.get("abilityGameID", 0), "?"),
                              "ability_id": e.get("abilityGameID", 0), "t": round(t, 1), "phase": ph,
                              "t_in_phase": round(tp, 1) if tp is not None else None})
            boss_casts, deaths = [], []
            try:
                boss_casts = _boss_cast_list(client, rep["code"], f, npc_names or [], names, f.get("name", ""))
                actor_names = {a["id"]: a["name"] for a in md.get("actors") or []}
                for d in client.deaths(rep["code"], f):
                    deaths.append({"player": actor_names.get(d.get("targetID"), "?"),
                                   "t": round((d["timestamp"] - f["startTime"]) / 1000, 1),
                                   "by": names.get(d.get("killingAbilityGameID") or d.get("abilityGameID") or 0, "")})
            except Exception as e:
                if verbose:
                    print(f"  (no boss casts/deaths for our pull {f['id']}: {e})")
            pulls.append({"code": rep["code"], "fight_id": f["id"], "url": f"https://www.warcraftlogs.com/reports/{rep['code']}#fight={f['id']}",
                          "date": rep["startTime"], "duration": tmp.duration, "kill": bool(f.get("kill")),
                          "pct": f.get("fightPercentage"), "phases": phases,
                          "healers": [{"name": h.name, "spec": h.spec_key} for h in healers], "casts": casts,
                          "boss_casts": boss_casts, "deaths": deaths})
        if len(pulls) >= n_pulls:
            break
    if verbose:
        print(f"  {len(pulls)} of our pulls read for comparison")
    return pulls


# ------------------------------------------------------- mythic healer count
def mythic_healer_counts(client: WCLClient, encounter_id: int, min_kills: int = 8, pages: int = 3,
                         verbose: bool = False) -> dict | None:
    """How many healers Mythic kill teams brought, from the boss's Mythic fight rankings.

    Returns None when there are fewer than min_kills Mythic kills to look at. Mythic is fixed at 20
    players so the healer count is a real decision there; Heroic flexes 10 to 30 and is skipped.
    """
    import statistics as st
    rows: list[tuple[int, float]] = []
    seen: set[tuple[str, int]] = set()
    for page in range(1, pages + 1):
        try:
            data = client.fight_rankings(encounter_id, DIFFICULTY["mythic"], page=page, metric="speed")
        except Exception as e:
            if verbose:
                print(f"  (mythic rankings page {page} failed: {e})")
            break
        ranks = data.get("rankings") or []
        for r in ranks:
            rep = r.get("report") or {}
            key = (rep.get("code"), rep.get("fightID"))
            if key in seen or not key[0]:
                continue
            seen.add(key)
            healers = r.get("healers")
            if healers is None:
                try:
                    pd = client.player_details(key[0], key[1])
                    healers = len(pd.get("healers") or [])
                except Exception:
                    continue
            dur = (r.get("duration") or 0) / 1000
            if healers and dur:
                rows.append((int(healers), dur))
        if not data.get("hasMorePages"):
            break
    if len(rows) < min_kills:
        if verbose:
            print(f"  only {len(rows)} Mythic kills found, skipping healer-count suggestion")
        return None
    by_n: dict[int, list[float]] = {}
    for n, d in rows:
        by_n.setdefault(n, []).append(d)
    dist = sorted(({"healers": n, "kills": len(ds), "share": round(len(ds) / len(rows), 2),
                    "median_kill": round(st.median(ds)), "fastest": round(min(ds))} for n, ds in by_n.items()),
                  key=lambda x: -x["kills"])
    return {"kills": len(rows), "distribution": dist, "suggested": dist[0]["healers"]}


def last_pull_times(client: WCLClient, guild_id: int, zone_id: int, encounters: list[dict],
                    recent_reports: int) -> dict[int, float]:
    """encounter id -> timestamp of our most recent pull of it on any difficulty (0 if never)."""
    out = {e["id"]: 0.0 for e in encounters}
    for rep in client.guild_reports(guild_id, zone_id, recent_reports):
        for f in client.report_fights(rep["code"]):
            eid = f.get("encounterID")
            if eid in out:
                out[eid] = max(out[eid], rep["startTime"] + f["startTime"])
    return out
