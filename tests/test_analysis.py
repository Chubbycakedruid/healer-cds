import tomllib
from pathlib import Path

from healer_cds import analysis
from healer_cds.demo import make_demo
from healer_cds.models import Cast, Healer, Kill, OurComp
from healer_cds.notes import build_note
from healer_cds.pipeline import _damage_series, _fuzzy, _healers_from_details

ROOT = Path(__file__).resolve().parent.parent
COOLDOWNS = tomllib.loads((ROOT / "cooldowns.toml").read_text())


def test_fuzzy_boss_names():
    names = ["Nek'zali the Soulcoiler", "The Coiled Altar", "Ula'tek"]
    assert _fuzzy("Coiled Altar", names) == "The Coiled Altar"
    assert _fuzzy("ula'tek", names) == "Ula'tek"
    assert _fuzzy("Ulatek", names) == "Ula'tek"
    assert _fuzzy("Nothing here", names) is None


def test_healers_from_player_details():
    pd = {"healers": [{"name": "Chubbycake", "id": 7, "type": "Druid", "specs": [{"spec": "Restoration", "count": 3}]}]}
    hs = _healers_from_details(pd)
    assert hs[0].spec_key == "Restoration Druid" and hs[0].actor_id == 7


def test_jaccard_multiset():
    assert analysis.jaccard_multiset(["A", "B"], ["A", "B"]) == 1.0
    assert analysis.jaccard_multiset(["A", "A"], ["A"]) == 0.5
    assert analysis.jaccard_multiset(["A"], ["B"]) == 0.0


def test_score_prefers_matching_comp_and_duration():
    ours = OurComp([Healer("x", "Restoration Druid"), Healer("y", "Holy Paladin")], 1, None, [], 0, [])
    good = Kill("a", 1, "g", "EU", 300, [Healer("p", "Restoration Druid"), Healer("q", "Holy Paladin")])
    bad = Kill("b", 1, "g", "EU", 500, [Healer("p", "Holy Priest"), Healer("q", "Holy Paladin")])
    sg, _ = analysis.score_kill(good, ours, 300, 0.7, 0.3)
    sb, _ = analysis.score_kill(bad, ours, 300, 0.7, 0.3)
    assert sg == 1.0 and sb < sg


def test_phase_of():
    k = Kill("a", 1, "g", "EU", 300, [], phases=[(1, 0.0), (2, 100.0), (3, 200.0)])
    assert k.phase_of(50) == (1, 50)
    assert k.phase_of(150) == (2, 50)
    assert k.phase_of(250) == (3, 50)


def test_clustering_finds_shared_timings_and_ignores_spam():
    kills = []
    for i in range(6):
        k = Kill(f"k{i}", 1, "g", "EU", 300, [Healer("d", "Restoration Druid", 1)], phases=[(1, 0.0), (2, 120.0)])
        for t in (30 + i, 150 + i):     # tranq used at roughly the same time in every kill
            c = Cast("Restoration Druid", "d", "Tranquility", 740, t)
            c.phase, c.t_in_phase = k.phase_of(t)
            k.casts.append(c)
        for t in range(0, 300, 7):       # rejuv spam
            c = Cast("Restoration Druid", "d", "Rejuvenation", 774, t)
            c.phase, c.t_in_phase = k.phase_of(t)
            k.casts.append(c)
        kills.append(k)
    assert analysis.phases_are_usable(kills)
    cl = analysis.cluster_cooldowns(kills, COOLDOWNS, gap=15, min_support=0.4, use_phases=True)
    tranq = [c for c in cl if c.ability == "Tranquility"]
    assert len(tranq) == 2
    assert [c.phase for c in tranq] == [1, 2]
    assert abs(tranq[1].median - 32.5) < 1      # 150+2.5 - 120
    assert all(c.support == 6 for c in tranq)
    assert not [c for c in cl if c.ability == "Rejuvenation"]


def test_note_format_and_ordering():
    ours, kills = make_demo("The Coiled Altar", COOLDOWNS)
    cl = analysis.cluster_cooldowns(kills, COOLDOWNS, 15, 0.4, True)
    cl = [c for c in cl if c.tier != "discovered" and c.spec_key in set(ours.healer_specs)]
    note = build_note(cl, ours, "Boss", use_phases=True)
    lines = note.splitlines()
    assert lines[0].startswith("{star}")
    assert all(l.startswith("{time:") and "{spell:" in l for l in lines[1:])
    # phase-relative timings must be ordered within each phase
    seen = []
    for l in lines[1:]:
        head = l.split("}")[0]           # {time:m:ss,pN
        ts, ph = head[6:].split(",p")
        m, s = ts.split(":")
        seen.append((int(ph), int(m) * 60 + int(s)))
    assert seen == sorted(seen)


def test_damage_series_sums_players_when_no_total():
    fight = {"startTime": 1000}
    g = {"series": [{"pointStart": 1000, "pointInterval": 2000, "data": [[1000, 10], [3000, 20]]},
                    {"pointStart": 1000, "pointInterval": 2000, "data": [[1000, 5], [3000, 5]]}]}
    s = _damage_series(g, fight)
    assert s == [(0.0, 7.5), (2.0, 12.5)]


def test_damage_peaks():
    curve = [(t, 1.0) for t in range(0, 100, 2)]
    curve[10] = (20, 50.0)
    curve[30] = (60, 40.0)
    peaks = analysis.damage_peaks(curve)
    assert [p[0] for p in peaks] == [20, 60]


def test_mechanic_attribution_and_exemplar():
    ours, kills = make_demo("The Coiled Altar", COOLDOWNS)
    cl = analysis.cluster_cooldowns(kills, COOLDOWNS, 15, 0.3, True)
    cl = [c for c in cl if c.spec_key in set(ours.healer_specs)]
    curve = analysis.average_damage_curve(kills)
    peaks = analysis.damage_peaks(curve)
    mech, peak_names = analysis.attribute_mechanics(kills, cl, peaks)
    assert mech and all(m in ("Fangs of the Crucible", "Eternal Nightfall", "Defilement of the Crucible", "Toxic Deluge", "Gloombomb", "Grim Guillotine") for m in mech.values())
    assert any(peak_names)
    ex = analysis.exemplar_sequences(kills, cl, ours.healer_specs)
    assert "Restoration Druid" in ex and ex["Restoration Druid"]["casts"]
    assert ex["Restoration Druid"]["score"] > 0



def test_planner_end_to_end():
    from healer_cds import planner
    ours, kills = make_demo("The Coiled Altar", COOLDOWNS)
    boss = planner.load_boss_file("The Coiled Altar")
    assert boss and boss["_file"] == "the-coiled-altar.toml"
    occ, unlisted = planner.mechanic_timeline(kills, boss, True)
    names = {o["mechanic"] for o in occ}
    assert "Fangs of the Crucible" in names and "Defilement of the Crucible" in names
    ev = planner.cooldown_evidence(kills, occ, ours.healer_specs, COOLDOWNS)
    assert len(ev) == len(occ)
    planner.apply_evidence(occ, ev)
    plan = planner.plan_team(occ, ev, ours, COOLDOWNS, {})
    assert plan["assignments"]
    # a cooldown is never assigned twice inside its own cooldown
    by = {}
    for a in plan["assignments"]:
        by.setdefault((a["healer"], a["ability"]), []).append(occ[a["occ"]]["abs_t"])
    cd = {(s, c["name"]): c["cd"] for s, l in COOLDOWNS.items() for c in l}
    for (h, ab), ts in by.items():
        spec = next(x.spec_key for x in ours.healers if x.name == h)
        ts.sort()
        assert all(b - a >= cd[(spec, ab)] * 0.9 - 1e-6 for a, b in zip(ts, ts[1:]))
    # absorbs only get a DR if the kills show DR being used there
    for a in plan["assignments"]:
        o = occ[a["occ"]]
        if o["type"] == "absorb" and a["kind"] == "dr":
            assert "dr" in o["cover"]
