"""Synthetic kills so the pipeline and dashboard can be exercised without API access."""
from __future__ import annotations

import random

from .models import Cast, Healer, Kill, OurComp

GUILDS = ["Echo", "Liquid", "Method", "Instant Dollars", "Pieces", "Exorsus", "Honestly", "Aversion",
          "Nurfed", "Midwinter", "Skyline", "Pescorus", "Fatsharkyes", "BDGG"]


def make_demo(boss: str, cooldowns: dict[str, list[dict]], seed: int = 7) -> tuple[OurComp, list[Kill]]:
    rng = random.Random(seed + len(boss))
    ours = OurComp(
        healers=[Healer("Chubbycake", "Restoration Druid"), Healer("Lumenpal", "Holy Paladin"),
                 Healer("Bubblewrap", "Discipline Priest"), Healer("Mistyfoot", "Mistweaver Monk")],
        pulls=41, best_pct=18.4, phases=[(1, 0.0), (2, 95.0)], longest_pull=310.0, source_reports=["demo"],
    )
    # canonical "true" plan the kills are sampled around
    base_dur = 330.0 if "Coiled" in boss else 410.0
    phases_true = [(1, 0.0), (2, 0.29 * base_dur), (3, 0.66 * base_dur)]
    plan = {
        "Restoration Druid": {"Tranquility": [(2, 20), (3, 60)], "Convoke the Spirits": [(1, 25), (1, 90), (2, 45), (3, 10), (3, 80)],
                              "Flourish": [(1, 40), (2, 22), (3, 62)], "Ironbark": [(1, 60), (2, 70)]},
        "Holy Paladin": {"Aura Mastery": [(1, 70), (3, 35)], "Avenging Wrath": [(1, 20), (2, 40), (3, 65)],
                         "Divine Toll": [(1, 15), (1, 75), (2, 30), (3, 20), (3, 80)]},
        "Discipline Priest": {"Power Word: Barrier": [(1, 72), (3, 8)], "Rapture": [(1, 18), (2, 18), (3, 30)],
                              "Evangelism": [(1, 22), (2, 22), (3, 34)], "Ultimate Penitence": [(2, 60)]},
        "Mistweaver Monk": {"Revival": [(2, 5), (3, 90)], "Celestial Conduit": [(1, 30), (2, 35), (3, 25), (3, 95)],
                            "Invoke Chi-Ji, the Red Crane": [(1, 10), (2, 42), (3, 40)]},
        "Restoration Shaman": {"Spirit Link Totem": [(2, 8)], "Healing Tide Totem": [(1, 70), (3, 50)]},
    }
    ids = {c["name"]: c["ids"][0] for cds in cooldowns.values() if isinstance(cds, list) for c in cds if c.get("ids")}
    kills: list[Kill] = []
    for i, g in enumerate(GUILDS):
        dur = base_dur * rng.uniform(0.88, 1.15)
        healers = [Healer("Rdruid" + str(i), "Restoration Druid", 1), Healer("Hpal" + str(i), "Holy Paladin", 2),
                   Healer("Disc" + str(i), "Discipline Priest", 3)]
        healers.append(Healer("Mw" + str(i), "Mistweaver Monk", 4) if rng.random() < 0.6
                       else Healer("Rsham" + str(i), "Restoration Shaman", 4))
        if rng.random() < 0.25:
            healers[2] = Healer("Hpriest" + str(i), "Holy Priest", 3)
        scale = dur / base_dur
        phases = [(pid, s * scale) for pid, s in phases_true]
        k = Kill(g + "-demo", i + 1, g, rng.choice(["EU", "EU", "US", "KR"]), dur, healers, phases)
        for h in healers:
            for ability, uses in plan.get(h.spec_key, {}).items():
                for pid, off in uses:
                    if rng.random() < 0.85:
                        pstart = next(s for p, s in phases if p == pid)
                        t = pstart + off * rng.uniform(0.95, 1.05) + rng.gauss(0, 3)
                        if 0 < t < dur:
                            c = Cast(h.spec_key, h.name, ability, ids.get(ability, 0), t)
                            c.phase, c.t_in_phase = k.phase_of(t)
                            k.casts.append(c)
            # filler spam so discovery has something to ignore
            for _ in range(60):
                t = rng.uniform(0, dur)
                c = Cast(h.spec_key, h.name, "Rejuvenation" if "Druid" in h.spec_key else "Holy Shock", 774, t)
                c.phase, c.t_in_phase = k.phase_of(t)
                k.casts.append(c)
            # a rare unlisted ability, to show discovery
            if "Druid" in h.spec_key:
                t = phases[1][1] + 3 + rng.gauss(0, 2)
                c = Cast(h.spec_key, h.name, "Grove Guardians", 102693, t)
                c.phase, c.t_in_phase = k.phase_of(t)
                k.casts.append(c)
        # damage curve: baseline + spikes near CD timings, with a named boss ability per spike
        mech_by_phase = {1: {20: "Fangs of the Crucible", 70: "Fangs of the Crucible", 45: "Toxic Deluge"},
                         2: {20: "Eternal Nightfall", 70: "Eternal Nightfall", 45: "Gloombomb"},
                         3: {20: "Defilement of the Crucible", 70: "Defilement of the Crucible", 45: "Grim Guillotine"}}
        for pid, s in phases:
            for off, mname in mech_by_phase.get(pid, {}).items():
                k.boss_casts.append((mname, round(s + off * scale + rng.gauss(0, 1.5), 1)))
        k.boss_casts.sort(key=lambda x: x[1])
        k.damage_abilities = {"Melee": [], "Toxic Pool": []}
        for step in range(int(dur / 2)):
            t = step * 2.0
            v = 90_000 + 25_000 * rng.random()
            k.damage_abilities["Melee"].append((t, 60_000))
            k.damage_abilities["Toxic Pool"].append((t, v - 60_000))
            spikes: dict = {}
            for pid, s in phases:
                for spike in (20, 70):
                    if abs(t - (s + spike * scale)) < 6:
                        v += 220_000
                        spikes[mech_by_phase[pid][spike]] = spikes.get(mech_by_phase[pid][spike], 0) + 220_000
                if abs(t - (s + 45 * scale)) < 8:
                    v += 90_000
                    spikes[mech_by_phase[pid][45]] = spikes.get(mech_by_phase[pid][45], 0) + 90_000
            for name in set(x for d in mech_by_phase.values() for x in d.values()):
                k.damage_abilities.setdefault(name, []).append((t, spikes.get(name, 0.0)))
            k.damage.append((t, v))
        kills.append(k)
    return ours, kills


def make_demo_pulls(boss: str, ours: OurComp, kills: list[Kill], n: int = 5, seed: int = 3) -> list[dict]:
    """Fake 'our' wipes: like the kills but noisier, later, and ending early."""
    rng = random.Random(seed + len(boss))
    ref = kills[0]
    out = []
    for i in range(n):
        wipe_at = ref.duration * rng.uniform(0.35, 0.9)
        phases = [(pid, s) for pid, s in ref.phases if s < wipe_at]
        casts = []
        for h in ours.healers:
            src = next((x for x in ref.healers if x.spec_key == h.spec_key), None)
            for c in ref.casts:
                if src and c.player == src.name and c.t < wipe_at and rng.random() < 0.7:
                    t = c.t + rng.gauss(6, 5)
                    if 0 < t < wipe_at:
                        tmp = Kill("x", 1, "us", "", wipe_at, [], phases)
                        ph, tp = tmp.phase_of(t)
                        casts.append({"player": h.name, "spec": h.spec_key, "ability": c.ability, "ability_id": c.ability_id,
                                      "t": round(t, 1), "phase": ph, "t_in_phase": round(tp, 1) if tp is not None else None})
        deaths = [{"player": rng.choice([h.name for h in ours.healers] + ["Dpsguy", "Tankman"]),
                   "t": round(wipe_at - rng.uniform(1, 25), 1), "by": rng.choice([n for n, _ in ref.boss_casts])} for _ in range(rng.randint(1, 3))]
        out.append({"code": f"ours{i}", "fight_id": i + 1, "url": "https://www.warcraftlogs.com/", "date": 0,
                    "boss_casts": [(n, t) for n, t in ref.boss_casts if t < wipe_at], "deaths": deaths,
                    "duration": wipe_at, "kill": False, "pct": round(100 - wipe_at / ref.duration * 100, 1),
                    "phases": phases, "healers": [{"name": h.name, "spec": h.spec_key} for h in ours.healers],
                    "casts": sorted(casts, key=lambda c: c["t"])})
    return out
