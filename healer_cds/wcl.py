"""Thin Warcraft Logs v2 (GraphQL) client using the client credentials flow.

Only public reports are readable this way. Rate limit is 3600 points/hour per client;
every query response includes rateLimitData so we can print it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
API_URL = "https://www.warcraftlogs.com/api/v2/client"

DIFFICULTY = {"lfr": 1, "normal": 3, "heroic": 4, "mythic": 5}


class WCLError(RuntimeError):
    pass


class WCLClient:
    def __init__(self, client_id: str, client_secret: str, cache_dir: Path | None = None,
                 verbose: bool = False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_dir = cache_dir
        self.verbose = verbose
        self._token: str | None = None
        self._token_expiry = 0.0
        self.points_spent = 0.0
        self.points_limit = 0
        self.session = requests.Session()
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ auth
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        r = self.session.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        if r.status_code == 401:
            raise WCLError(
                "Warcraft Logs rejected the client ID / secret (401). "
                "Check config.toml against https://www.warcraftlogs.com/api/clients"
            )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 3600))
        return self._token

    # ----------------------------------------------------------------- query
    def query(self, gql: str, variables: dict[str, Any] | None = None, cache_key: str | None = None,
              fresh: bool = False) -> dict:
        """Run a GraphQL query. Results with a cache_key are cached on disk (finished reports never change).
        fresh=True skips the cache read (for a report that is still being logged tonight) but still writes it."""
        if cache_key and self.cache_dir and not fresh:
            p = self.cache_dir / f"{cache_key}.json"
            if p.exists():
                return json.loads(p.read_text())

        payload = {"query": gql, "variables": variables or {}}
        for attempt in range(4):
            r = self.session.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._get_token()}"},
                timeout=120,
            )
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            break
        r.raise_for_status()
        body = r.json()
        if "errors" in body and body["errors"]:
            msg = "; ".join(e.get("message", str(e)) for e in body["errors"])
            if body.get("data") is None:
                raise WCLError(f"GraphQL error: {msg}")
            if self.verbose:
                print(f"  (partial GraphQL errors: {msg})")
        data = body.get("data") or {}
        rl = data.get("rateLimitData")
        if rl:
            self.points_spent = rl.get("pointsSpentThisHour", self.points_spent)
            self.points_limit = rl.get("limitPerHour", self.points_limit)
        if cache_key and self.cache_dir:
            (self.cache_dir / f"{cache_key}.json").write_text(json.dumps(data))
        return data

    # --------------------------------------------------------- convenience
    RL = "rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }"

    def zones(self) -> list[dict]:
        q = "{ worldData { zones { id name encounters { id name } } } %s }" % self.RL
        return self.query(q, cache_key="zones")["worldData"]["zones"]

    def guild_reports(self, guild_id: int, zone_id: int, limit: int = 10) -> list[dict]:
        q = """
        query($g:Int!,$z:Int!,$l:Int!){
          reportData { reports(guildID:$g, zoneID:$z, limit:$l) {
            data { code title startTime endTime } } }
          %s }""" % self.RL
        # not cached: new reports appear over time
        return self.query(q, {"g": guild_id, "z": zone_id, "l": limit})["reportData"]["reports"]["data"]

    def report_fights(self, code: str, encounter_id: int | None = None, difficulty: int | None = None,
                      fresh: bool = False) -> list[dict]:
        q = """
        query($c:String!,$e:Int,$d:Int){
          reportData { report(code:$c) {
            fights(encounterID:$e, difficulty:$d) {
              id encounterID name difficulty kill startTime endTime fightPercentage
              friendlyPlayers
              phaseTransitions { id startTime }
            } } }
          %s }""" % self.RL
        key = f"fights_{code}_{encounter_id}_{difficulty}"
        return self.query(q, {"c": code, "e": encounter_id, "d": difficulty}, cache_key=key, fresh=fresh)["reportData"]["report"]["fights"]

    def player_details(self, code: str, fight_id: int) -> dict:
        """Returns {"tanks": [...], "healers": [...], "dps": [...]} with name/id/type/specs."""
        q = """
        query($c:String!,$f:[Int]!){
          reportData { report(code:$c) { playerDetails(fightIDs:$f) } }
          %s }""" % self.RL
        raw = self.query(q, {"c": code, "f": [fight_id]}, cache_key=f"pd_{code}_{fight_id}")
        pd = raw["reportData"]["report"]["playerDetails"]
        # shape: {"data": {"playerDetails": {"tanks": [...], ...}}}
        if isinstance(pd, dict) and "data" in pd:
            pd = pd["data"].get("playerDetails", pd["data"])
        return pd or {}

    def master_data(self, code: str) -> dict:
        q = """
        query($c:String!){
          reportData { report(code:$c) { masterData {
            abilities { gameID name type }
            actors(type:"Player") { id name type subType server }
          } } }
          %s }""" % self.RL
        return self.query(q, {"c": code}, cache_key=f"md_{code}")["reportData"]["report"]["masterData"]

    def npc_actors(self, code: str) -> list[dict]:
        q = """
        query($c:String!){
          reportData { report(code:$c) { masterData {
            actors(type:"NPC") { id name gameID subType }
          } } }
          %s }""" % self.RL
        return self.query(q, {"c": code}, cache_key=f"npc_{code}")["reportData"]["report"]["masterData"]["actors"] or []

    def enemy_casts(self, code: str, fight: dict, source_ids: list[int]) -> list[dict]:
        """Cast and begincast events by the given enemy actors during a fight."""
        events: list[dict] = []
        for sid in source_ids:
            start = fight["startTime"]
            page = 0
            while start is not None and page < 20:
                q = """
                query($c:String!,$f:[Int]!,$s:Float!,$e:Float!,$src:Int!){
                  reportData { report(code:$c) {
                    events(fightIDs:$f, startTime:$s, endTime:$e, dataType:Casts,
                           sourceID:$src, hostilityType:Enemies, limit:10000)
                    { data nextPageTimestamp } } }
                  %s }""" % self.RL
                key = f"ecasts_{code}_{fight['id']}_{sid}_{page}"
                res = self.query(q, {"c": code, "f": [fight["id"]], "s": start,
                                     "e": fight["endTime"], "src": sid}, cache_key=key)
                ev = res["reportData"]["report"]["events"]
                events.extend(e for e in (ev.get("data") or []) if e.get("type") in ("cast", "begincast"))
                start = ev.get("nextPageTimestamp")
                page += 1
        return events

    def deaths(self, code: str, fight: dict) -> list[dict]:
        q = """
        query($c:String!,$f:[Int]!,$s:Float!,$e:Float!){
          reportData { report(code:$c) {
            events(fightIDs:$f, startTime:$s, endTime:$e, dataType:Deaths, hostilityType:Friendlies, limit:1000)
            { data } } } %s }""" % self.RL
        res = self.query(q, {"c": code, "f": [fight["id"]], "s": fight["startTime"], "e": fight["endTime"]},
                         cache_key=f"deaths_{code}_{fight['id']}")
        return (res["reportData"]["report"]["events"] or {}).get("data") or []

    def casts(self, code: str, fight: dict, source_ids: list[int]) -> list[dict]:
        """All cast events for the given source actors during a fight. Paginates."""
        events: list[dict] = []
        for sid in source_ids:
            start = fight["startTime"]
            page = 0
            while start is not None and page < 20:
                q = """
                query($c:String!,$f:[Int]!,$s:Float!,$e:Float!,$src:Int!){
                  reportData { report(code:$c) {
                    events(fightIDs:$f, startTime:$s, endTime:$e, dataType:Casts,
                           sourceID:$src, hostilityType:Friendlies, limit:10000)
                    { data nextPageTimestamp } } }
                  %s }""" % self.RL
                key = f"casts_{code}_{fight['id']}_{sid}_{page}"
                res = self.query(q, {"c": code, "f": [fight["id"]], "s": start,
                                     "e": fight["endTime"], "src": sid}, cache_key=key)
                ev = res["reportData"]["report"]["events"]
                events.extend(e for e in (ev.get("data") or []) if e.get("type") == "cast")
                start = ev.get("nextPageTimestamp")
                page += 1
        return events

    def damage_taken_graph(self, code: str, fight: dict) -> dict:
        q = """
        query($c:String!,$f:[Int]!,$s:Float!,$e:Float!){
          reportData { report(code:$c) {
            graph(fightIDs:$f, startTime:$s, endTime:$e, dataType:DamageTaken, hostilityType:Friendlies)
          } } %s }""" % self.RL
        res = self.query(q, {"c": code, "f": [fight["id"]], "s": fight["startTime"],
                             "e": fight["endTime"]}, cache_key=f"dmg_{code}_{fight['id']}")
        g = res["reportData"]["report"]["graph"]
        if isinstance(g, dict) and "data" in g:
            g = g["data"]
        return g or {}

    def damage_taken_by_ability(self, code: str, fight: dict) -> dict:
        q = """
        query($c:String!,$f:[Int]!,$s:Float!,$e:Float!){
          reportData { report(code:$c) {
            graph(fightIDs:$f, startTime:$s, endTime:$e, dataType:DamageTaken, hostilityType:Friendlies, viewBy:Ability)
          } } %s }""" % self.RL
        res = self.query(q, {"c": code, "f": [fight["id"]], "s": fight["startTime"],
                             "e": fight["endTime"]}, cache_key=f"dmgab_{code}_{fight['id']}")
        g = res["reportData"]["report"]["graph"]
        if isinstance(g, dict) and "data" in g:
            g = g["data"]
        return g or {}

    def character_rankings(self, encounter_id: int, difficulty: int, class_name: str,
                           spec_name: str, page: int = 1, metric: str = "hps") -> dict:
        q = """
        query($e:Int!,$d:Int,$cls:String,$spec:String,$p:Int,$m:CharacterRankingMetricType){
          worldData { encounter(id:$e) {
            characterRankings(difficulty:$d, className:$cls, specName:$spec, page:$p, metric:$m)
          } } %s }""" % self.RL
        res = self.query(q, {"e": encounter_id, "d": difficulty, "cls": class_name,
                             "spec": spec_name, "p": page, "m": metric})
        return res["worldData"]["encounter"]["characterRankings"] or {}

    def fight_rankings(self, encounter_id: int, difficulty: int, page: int = 1, metric: str = "speed") -> dict:
        q = """
        query($e:Int!,$d:Int,$p:Int,$m:FightRankingMetricType){
          worldData { encounter(id:$e) {
            fightRankings(difficulty:$d, page:$p, metric:$m)
          } } %s }""" % self.RL
        res = self.query(q, {"e": encounter_id, "d": difficulty, "p": page, "m": metric})
        return res["worldData"]["encounter"]["fightRankings"] or {}
