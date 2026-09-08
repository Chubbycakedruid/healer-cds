from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Healer:
    name: str
    spec_key: str          # e.g. "Restoration Druid"
    actor_id: int | None = None


@dataclass
class Cast:
    spec_key: str
    player: str
    ability: str
    ability_id: int
    t: float               # seconds from pull
    phase: int | None = None
    t_in_phase: float | None = None


@dataclass
class Kill:
    code: str
    fight_id: int
    guild: str
    region: str
    duration: float                        # seconds
    healers: list[Healer]
    phases: list[tuple[int, float]] = field(default_factory=list)   # (phase id, start offset s)
    casts: list[Cast] = field(default_factory=list)
    damage: list[tuple[float, float]] = field(default_factory=list)  # (t, dtps)
    damage_abilities: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # boss ability -> (t, dtps)
    boss_casts: list[tuple[str, float]] = field(default_factory=list)   # (ability name, seconds from pull)
    score: float = 0.0
    match_notes: str = ""

    @property
    def url(self) -> str:
        return f"https://www.warcraftlogs.com/reports/{self.code}#fight={self.fight_id}"

    @property
    def healer_specs(self) -> list[str]:
        return sorted(h.spec_key for h in self.healers)

    def phase_of(self, t: float) -> tuple[int | None, float | None]:
        if not self.phases:
            return None, None
        cur_id, cur_start = None, 0.0
        for pid, start in sorted(self.phases, key=lambda x: x[1]):
            if t >= start:
                cur_id, cur_start = pid, start
        if cur_id is None:
            # before first transition: treat as phase 1 from pull
            return 1, t
        return cur_id, t - cur_start


@dataclass
class OurComp:
    healers: list[Healer]
    pulls: int
    best_pct: float | None
    phases: list[tuple[int, float]]
    longest_pull: float
    source_reports: list[str]

    @property
    def healer_specs(self) -> list[str]:
        return sorted(h.spec_key for h in self.healers)
