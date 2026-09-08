"""Command line entry point.

    python run.py                 # live: uses config.toml
    python run.py --demo          # synthetic data, no API needed
    python run.py --boss "Ula'tek" --difficulty mythic
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import tomllib
from collections import Counter
from pathlib import Path

from . import analysis, pipeline, planner
from .analysis import CDCluster, fmt_time
from .dashboard import write_dashboard
from .models import Kill, OurComp
from .notes import build_note, build_nsrt, build_plan_text
from .wcl import DIFFICULTY, WCLClient, WCLError

ROOT = Path(__file__).resolve().parent.parent


def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_cooldowns(path: Path) -> dict[str, list[dict]]:
    return load_toml(path)


def analyse_boss(name: str, ours: OurComp, kills: list[Kill], cfg: dict, cooldowns: dict,
                 encounter_id: int = 0, difficulty: str = "heroic", our_pulls: list[dict] | None = None) -> dict:
    a = cfg["analysis"]
    use_phases = analysis.phases_are_usable(kills)
    # cluster with a low floor; the dashboard applies the configured threshold and lets you drag it
    clusters = analysis.cluster_cooldowns(kills, cooldowns, gap=a["cluster_gap"], min_support=min(0.15, a["min_support"]),
                                         use_phases=use_phases, discover_unlisted=a.get("discover_unlisted", True))
    our_specs = set(ours.healer_specs)
    clusters = [c for c in clusters if c.spec_key in our_specs]
    listed_and_relevant = [c for c in clusters if c.tier != "discovered"
                           and c.support_pct >= a["min_support"] - 1e-9]
    discovered = sorted({f"{c.spec_key}: {c.ability} (#{c.ability_id}) around {fmt_time(c.abs_median)}"
                         for c in clusters if c.tier == "discovered"})
    curve = analysis.average_damage_curve(kills)
    peaks = analysis.damage_peaks(curve)
    mech_by_cluster, peak_mechs = analysis.attribute_mechanics(kills, clusters, peaks)
    # canonical ids for exemplar casts: map (spec, ability) -> id used by the clusters
    canon = {(c.spec_key, c.ability): c.ability_id for c in clusters}
    exemplars = analysis.exemplar_sequences(kills, clusters, list(our_specs))
    for spec, ex in exemplars.items():
        for c in ex["casts"]:
            c["ability_id"] = canon.get((spec, c["ability"]), c["ability_id"])
    boss_file = planner.load_boss_file(name)
    occurrences, unlisted_boss = planner.mechanic_timeline(kills, boss_file, use_phases, min_support=a["min_support"])
    evidence = planner.cooldown_evidence(kills, occurrences, list(our_specs), cooldowns)
    planner.apply_evidence(occurrences, evidence, kind_threshold=a.get("evidence_threshold", 0.25))
    # what our healers actually have: abilities seen in our own pulls, else anything the kills' healers cast
    owned: set[tuple[str, str]] = set()
    for pl in our_pulls or []:
        for c in pl["casts"]:
            owned.add((c["spec"], c["ability"]))
    # any spec our pulls did not show us falls back to what that spec cast in the kills
    seen_specs = {sp for sp, _ in owned}
    owned |= {(c.spec_key, c.ability) for k in kills for c in k.casts if c.spec_key not in seen_specs}
    team_plan = planner.plan_team(occurrences, evidence, ours, cooldowns, canon, owned=owned)
    listed_names = {(spec, c["name"].lower()) for spec, lst in cooldowns.items() for c in lst}
    pulls_out = []
    for pl in our_pulls or []:
        keep = [c for c in pl["casts"] if (c["spec"], c["ability"].lower()) in listed_names]
        for c in keep:
            c["ability_id"] = canon.get((c["spec"], c["ability"]), c["ability_id"])
        pulls_out.append({**pl, "casts": keep})
    target = statistics.median([k.duration for k in kills]) if kills else 0
    # reference phase timings: median start of each phase id across kills
    ph: dict[int, list[float]] = {}
    for k in kills:
        for pid, s in k.phases:
            ph.setdefault(pid, []).append(s)
    phases_ref = sorted((pid, statistics.median(v)) for pid, v in ph.items())
    overrides = (cfg.get("output") or {}).get("names") or {}
    notes = {
        "phased": build_note(listed_and_relevant, ours, name, use_phases=True, overrides=overrides),
        "absolute": build_note(listed_and_relevant, ours, name, use_phases=False, overrides=overrides),
        "plan": build_plan_text(listed_and_relevant, ours, use_phases),
    }
    nsrt = {}
    for h in ours.healers:
        nsrt[h.name] = {
            "major": build_nsrt(listed_and_relevant, h.name, h.spec_key, name, encounter_id, difficulty, use_phases),
            "all": build_nsrt(listed_and_relevant, h.name, h.spec_key, name, encounter_id, difficulty, use_phases, True),
        }
    return {
        "name": name, "use_phases": use_phases, "target_duration": target,
        "ours": {"healers": [{"name": h.name, "spec": h.spec_key} for h in ours.healers], "pulls": ours.pulls,
                 "best_pct": ours.best_pct, "longest_pull": ours.longest_pull, "phases": ours.phases},
        "kills": [{"code": k.code, "fight_id": k.fight_id, "guild": k.guild, "region": k.region, "duration": k.duration,
                   "score": k.score, "notes": k.match_notes, "url": k.url, "healer_specs": k.healer_specs,
                   "phases": k.phases} for k in kills],
        "clusters": [{**_cluster_dict(c), "mechanic": mech_by_cluster.get(i)} for i, c in enumerate(clusters)],
        "peak_mechanics": peak_mechs, "exemplars": exemplars, "our_pulls": pulls_out,
        "mechanics": occurrences, "evidence": evidence, "team_plan": team_plan, "unlisted_boss_casts": unlisted_boss,
        "boss_file": (boss_file or {}).get("_file"),
        "damage": [[round(t, 1), round(v)] for t, v in curve], "peaks": [[round(t, 1), round(v)] for t, v in peaks],
        "phases_ref": phases_ref, "notes": notes, "nsrt": nsrt, "discovered": discovered,
        "kills_with_spec": {spec: sum(1 for k in kills if spec in k.healer_specs) for spec in our_specs},
        "encounter_id": encounter_id, "difficulty": difficulty,
    }


def team_plan_text(r: dict) -> str:
    occ = r["mechanics"]; plan = r["team_plan"]
    by_occ: dict[int, list[dict]] = {}
    for a in plan["assignments"]:
        by_occ.setdefault(a["occ"], []).append(a)
    lines = []
    for i, o in enumerate(occ):
        when = f"P{o['phase']} {fmt_time(o['t'])}" if o.get("phase") is not None else fmt_time(o["abs_t"])
        who = ", ".join(f"{a['healer']} {a['ability']}" for a in by_occ.get(i, [])) or ("GAP" if i in plan["gaps"] else "-")
        lines.append(f"{when:>10}  {o['mechanic']:<28} {who}")
    return "\n".join(lines)


def _cluster_dict(c: CDCluster) -> dict:
    return {"spec": c.spec_key, "ability": c.ability, "ability_id": c.ability_id, "tier": c.tier, "phase": c.phase,
            "median": c.median, "spread": c.spread, "support": c.support, "total": c.total_kills,
            "abs_median": c.abs_median, "players": c.players, "cd": c.cd}


def _manual_comp(spec: list[str] | None) -> OurComp | None:
    """["Chubbycake:Restoration Druid", "Smollee:Restoration Shaman"] -> OurComp"""
    if not spec:
        return None
    from .analysis import SPEC_TO_CLASS
    from .models import Healer
    healers = []
    for item in spec:
        name, _, sp = item.partition(":")
        sp = sp.strip()
        match = next((k for k in SPEC_TO_CLASS if k.lower() == sp.lower()), None)
        if not match:
            sys.exit(f"Unknown healer spec '{sp}' in healers list. Use one of: {', '.join(SPEC_TO_CLASS)}")
        healers.append(Healer(name=name.strip(), spec_key=match))
    return OurComp(healers=healers, pulls=0, best_pct=None, phases=[], longest_pull=0, source_reports=[])


def _client(cfg: dict, verbose: bool) -> WCLClient:
    """Credentials from the environment (GitHub Actions) or config.toml (your PC)."""
    w = cfg.get("wcl", {})
    cid = os.environ.get("WCL_CLIENT_ID") or w.get("client_id", "")
    sec = os.environ.get("WCL_CLIENT_SECRET") or w.get("client_secret", "")
    if not cid or not sec or "PASTE" in cid or "PASTE" in sec or "FROM_ENV" in cid:
        sys.exit("No Warcraft Logs credentials: fill in [wcl] in config.toml, or set WCL_CLIENT_ID / WCL_CLIENT_SECRET.")
    return WCLClient(cid, sec, cache_dir=ROOT / ".cache", verbose=verbose)


def refresh_pulls_only(cfg: dict, cooldowns: dict, verbose: bool) -> list[dict]:
    """Fast mid-raid refresh: keep the last full analysis, re-read only OUR recent pulls.

    Touches nothing about the kill data or the plan, so it is cheap (a handful of API calls for the
    new pulls) and safe to run between pulls."""
    path = ROOT / cfg["output"].get("dir", "out") / "analysis.json"
    if not path.exists():
        sys.exit("No previous full analysis found (out/analysis.json). Run the full analysis once first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    client = _client(cfg, verbose)
    g = cfg["guild"]
    zone = pipeline.resolve_zone(client, g["raid"])
    listed_names = {(spec, c["name"].lower()) for spec, lst in cooldowns.items() for c in lst}
    for r in data["bosses"]:
        enc = pipeline.resolve_encounter(zone, r["name"])
        diff = DIFFICULTY[r["difficulty"].lower()]
        npcs = (planner.load_boss_file(r["name"]) or {}).get("npcs", [])
        canon = {(c["spec"], c["ability"]): c["ability_id"] for c in r["clusters"]}
        try:
            pulls = pipeline.our_pull_details(client, g["id"], zone["id"], enc["id"], diff,
                                              g.get("recent_reports", 8), g.get("compare_pulls", 6), verbose, npcs, live=True)
        except WCLError as e:
            print(f"  {r['name']} ({r['difficulty']}): {e}")
            continue
        out = []
        for pl in pulls:
            keep = [c for c in pl["casts"] if (c["spec"], c["ability"].lower()) in listed_names]
            for c in keep:
                c["ability_id"] = canon.get((c["spec"], c["ability"]), c["ability_id"])
            out.append({**pl, "casts": keep})
        if out:
            r["our_pulls"] = out
            print(f"  {r['name']} ({r['difficulty']}): {len(out)} pulls, newest {fmt_time(out[0]['duration'])} "
                  f"{'kill' if out[0]['kill'] else 'wipe'}")
        else:
            print(f"  {r['name']} ({r['difficulty']}): no pulls yet")
    data["pulls_refreshed"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return data


def run_live(cfg: dict, cooldowns: dict, bosses: list[str], difficulties: list[str], verbose: bool,
             healers_override: list[str] | None = None) -> list[dict]:
    client = _client(cfg, verbose)
    g, m = cfg["guild"], cfg["matching"]
    print(f"Resolving raid '{g['raid']}' ...")
    zone = pipeline.resolve_zone(client, g["raid"])
    encounters = [pipeline.resolve_encounter(zone, b) for b in bosses] if bosses else list(zone["encounters"])
    print(f"  {len(encounters)} bosses x {', '.join(difficulties)}")
    results: list[dict] = []
    last_comp: OurComp | None = None
    manual = _manual_comp(healers_override or g.get("healers"))
    min_kills = m.get("min_kills", 4)
    for enc in encounters:
        comp_by_diff: dict[str, OurComp] = {}
        for difficulty in difficulties:
            diff = DIFFICULTY[difficulty.lower()]
            print(f"\n== {enc['name']} ({difficulty}) ==")
            if client.points_limit and client.points_spent > 0.92 * client.points_limit:
                print("  Warcraft Logs hourly API budget nearly used up; stopping here. Run again in an hour for the rest.")
                break
            try:
                ours = pipeline.our_comp(client, g["id"], zone["id"], enc["id"], diff, g.get("recent_reports", 8), verbose)
                if ours is not None:
                    comp_by_diff[difficulty] = ours
                else:
                    other = next((c for c in comp_by_diff.values()), None)
                    src = other or manual or last_comp
                    if src is None:
                        print(f"  No pulls of {enc['name']} on any difficulty in your recent logs and no healer list in "
                              f"config. Skipping until you pull it (or add healers = [...] under [guild]).")
                        continue
                    ours = OurComp(healers=src.healers, pulls=0, best_pct=None, phases=[], longest_pull=0, source_reports=[])
                    print("  No pulls at this difficulty yet; using " + ("the lineup from your other-difficulty pulls" if other
                          else "the healer list from config" if manual else "the previous boss's lineup") + ".")
                last_comp = ours
                print("  Healers: " + ", ".join(f"{h.name} ({h.spec_key})" for h in ours.healers))
                cands = pipeline.candidate_kills(client, enc["id"], diff, ours, m["candidates_per_spec"], m.get("regions", []), verbose)
                if len(cands) < min_kills:
                    print(f"  Only {len(cands)} {difficulty} kills with your healer specs on Warcraft Logs, not enough to plan from. Skipping.")
                    continue
                print(f"  {len(cands)} candidate kills, reading their comps ...")
                chosen, target = pipeline.enrich_and_rank(client, cands, ours, m.get("target_duration", 0),
                                                          m["weight_healer_comp"], m["weight_duration"], m["kills_to_analyse"], verbose)
                print(f"  Analysing {len(chosen)} best matches (target kill time {fmt_time(target)}) ...")
                npcs = (planner.load_boss_file(enc["name"]) or {}).get("npcs", [])
                for k in chosen:
                    pipeline.load_fight_detail(client, k, ours.healer_specs, verbose, npcs)
                n_cmp = g.get("compare_pulls", 6)
                our_pulls = []
                if ours.pulls and n_cmp:
                    print(f"  Reading our last {n_cmp} pulls for comparison ...")
                    our_pulls = pipeline.our_pull_details(client, g["id"], zone["id"], enc["id"], diff,
                                                          g.get("recent_reports", 8), n_cmp, verbose, npcs)
                res = analyse_boss(enc["name"], ours, chosen, cfg, cooldowns, enc["id"], difficulty, our_pulls)
                if difficulty.lower() == "mythic":
                    print("  Checking Mythic healer counts ...")
                    res["mythic_healers"] = pipeline.mythic_healer_counts(client, enc["id"], g.get("mythic_min_kills", 8), verbose=verbose)
                results.append(res)
                print(f"  API points used this hour: {client.points_spent:.0f}/{client.points_limit or '?'}")
            except WCLError as e:
                print(f"  Skipped: {e}")
        else:
            continue
        break   # budget exhausted
    return results


def run_demo(cfg: dict, cooldowns: dict, bosses: list[str]) -> list[dict]:
    from .demo import make_demo
    results = []
    for boss in bosses or ["The Coiled Altar", "Ula'tek"]:
      for difficulty in ("heroic", "mythic"):
        ours, kills = make_demo(boss, cooldowns, seed=7 if difficulty == "heroic" else 11)
        from .demo import make_demo_pulls
        our_pulls = make_demo_pulls(boss, ours, kills)
        m = cfg["matching"]
        target = statistics.median(k.duration for k in kills)
        for k in kills:
            k.score, k.match_notes = analysis.score_kill(k, ours, target, m["weight_healer_comp"], m["weight_duration"])
        kills.sort(key=lambda k: -k.score)
        res = analyse_boss(boss, ours, kills[: m["kills_to_analyse"]], cfg, cooldowns,
                           3429 if "Coiled" in boss else 0, difficulty, our_pulls)
        res["mythic_healers"] = {"kills": 37, "suggested": 4, "distribution": [
            {"healers": 4, "kills": 24, "share": 0.65, "median_kill": 452, "fastest": 401},
            {"healers": 5, "kills": 11, "share": 0.30, "median_kill": 478, "fastest": 430},
            {"healers": 3, "kills": 2, "share": 0.05, "median_kill": 418, "fastest": 410}]} if ("Coiled" in boss and difficulty == "mythic") else None
        results.append(res)
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Healer cooldown timings from Warcraft Logs kills matching your comp.")
    p.add_argument("--config", default=str(ROOT / "config.toml"))
    p.add_argument("--cooldowns", default=str(ROOT / "cooldowns.toml"))
    p.add_argument("--boss", action="append", help="boss name (repeatable); defaults to config")
    p.add_argument("--difficulty", help="heroic | mythic | normal; defaults to config")
    p.add_argument("--demo", action="store_true", help="use synthetic data, no API calls")
    p.add_argument("--pulls-only", action="store_true",
                   help="fast mid-raid refresh: re-read only our recent pulls, keep the last full analysis")
    p.add_argument("--healers", action="append",
                   help='pin the healer lineup, e.g. --healers "Chubbycake:Restoration Druid" (repeatable)')
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        if args.demo:
            cfg_path = ROOT / "config.example.toml"
        else:
            sys.exit(f"{cfg_path} not found. Copy config.example.toml to config.toml and fill it in.")
    cfg = load_toml(cfg_path)
    cooldowns = load_cooldowns(Path(args.cooldowns))
    bosses = args.boss or cfg["guild"].get("bosses", [])
    difficulties = [args.difficulty] if args.difficulty else cfg["guild"].get("difficulties") or [cfg["guild"].get("difficulty", "heroic")]

    out_dir = ROOT / cfg["output"].get("dir", "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.pulls_only:
            data = refresh_pulls_only(cfg, cooldowns, args.verbose)
            results = data["bosses"]
        else:
            results = run_demo(cfg, cooldowns, bosses) if args.demo else run_live(cfg, cooldowns, bosses, difficulties, args.verbose, args.healers)
            if not results:
                sys.exit("Nothing to report.")
            data = {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "guild": f"guild {cfg['guild']['id']}",
                    "difficulty": " / ".join(d.capitalize() for d in difficulties), "demo": args.demo, "bosses": results,
                    "min_support": cfg["analysis"]["min_support"]}
    except WCLError as e:
        sys.exit(f"\nError: {e}")
    (out_dir / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
    write_dashboard(data, out_dir / "dashboard.html")
    (out_dir / "index.html").write_text('<meta http-equiv="refresh" content="0; url=dashboard.html">', encoding="utf-8")
    if args.pulls_only:
        print(f"\nPulls refreshed. Dashboard: {out_dir / 'dashboard.html'}")
        return 0
    for r in results:
        slug = "".join(ch for ch in (r["name"] + "-" + r.get("difficulty", "")).lower().replace(" ", "-") if ch.isalnum() or ch == "-")
        (out_dir / f"{slug}-notes.txt").write_text(
            f"# {r['name']} - phase-relative\n{r['notes']['phased']}\n\n# {r['name']} - absolute\n"
            f"{r['notes']['absolute']}\n\n# plan\n{r['notes']['plan']}\n"
            + "".join(f"\n# NSRT dynamic timer note for {h}\n{v['major']}\n" for h, v in r["nsrt"].items())
            + "\n# Team coverage plan\n" + team_plan_text(r) + "\n",
            encoding="utf-8")
        print(f"\n{r['name']} ({r.get('difficulty','')}): {len([c for c in r['clusters'] if c['tier']=='major'])} major CD timings from "
              f"{len(r['kills'])} kills -> {slug}-notes.txt")
        print(r["notes"]["phased" if r["use_phases"] else "absolute"])
    print(f"\nDashboard: {out_dir / 'dashboard.html'}")
    return 0
