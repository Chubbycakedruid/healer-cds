# Healer Cooldown Planner

Pulls top kills of your prog boss from Warcraft Logs, keeps the ones whose healer lineup and kill time
look like yours, works out when their healers actually pressed their big cooldowns, and turns that into
raid notes you can paste into MRT / Liquid / Northern Sky plus a dashboard you can share with the healing team.

It does what lorrgs.io does (top-parse cooldown usage) but filtered to *your* comp, aligned by phase,
and with the raid damage curve underneath so you can see what each cooldown is covering.

## Setup (once, about 5 minutes)

1. Install Python 3.11 or newer from https://www.python.org/downloads/ (tick "Add Python to PATH" on Windows).
2. Unzip this folder somewhere sensible, open a terminal in it and run:

       pip install -r requirements.txt

3. `config.toml` is already filled in with your Warcraft Logs client ID and secret and your guild ID.
   If you ever make a new client at https://www.warcraftlogs.com/api/clients, paste the new values in there.
4. Check `[guild]` in `config.toml`: raid name, difficulty and the bosses you are progging.

## Running it

    python run.py                          # bosses and difficulty from config.toml
    python run.py --boss "Ula'tek"         # one boss
    python run.py --difficulty mythic      # override difficulty
    python run.py -v                       # chatty output (shows which kills were picked and why)
    python run.py --demo                   # synthetic data, no API needed, good for checking the dashboard

Output goes to `out/`:

- `out/dashboard.html`  open in a browser. Timeline, notes with copy buttons, every timing with how many
  kills agree, and the list of kills used with links back to Warcraft Logs.
- `out/<boss>-notes.txt`  the raid note text (phase-relative and absolute versions plus a plain plan).

Reports are cached in `.cache/` so re-running is cheap. Delete that folder if you want a fresh pull.
Your Warcraft Logs client gets 3600 API points per hour; one boss with 12 kills is usually 100 to 250 points.

## How it decides

1. **Your comp**: scans your guild's recent reports for pulls of the boss at that difficulty and takes the
   most common healer lineup from the latest pulls (names too, for the note).
2. **Candidate kills**: for each healer spec in your team, pulls the top HPS parses on the boss
   (`candidates_per_spec` each) and collects the unique kills behind them.
3. **Matching**: each kill is scored 70% on how closely its healer specs match yours (Jaccard on the multiset,
   so two resto druids vs one counts) and 30% on how close its kill time is to the target. The target is the
   median of the candidate kills unless you set `target_duration`. Top `kills_to_analyse` are kept.
4. **Cooldown timings**: every cast by the healers in those kills whose spec is also in your team is pulled.
   Casts of the abilities in `cooldowns.toml` are grouped across kills; if most kills carry phase transition
   data the grouping is done on time-since-phase-start, otherwise on time-since-pull. A group is reported
   when at least `min_support` of the kills have a cast there. Spread shows how tightly they agree.
5. **Discovery**: abilities not in `cooldowns.toml` that healers cast rarely (a few times a kill) and
   consistently are listed at the bottom of the dashboard. If one is a real cooldown (Blizzard renamed
   something, a new talent), add it to `cooldowns.toml` and it goes on the note next run.

## The team coverage planner

This is the part that plans for a healing team rather than copying five parsers. It works from the boss, not the healers:

1. **Mechanic timeline**: the boss's own cast log from each kill (Fangs of the Crucible, Eternal Nightfall and so on)
   is clustered across kills into occurrences per phase, with the damage each one actually did.
2. **Mechanic reference**: `bosses/<boss>.toml` says what each mechanic is (burst, DoT, healing absorb, tank hit,
   control), what kind of cooldown fits it (throughput, sustained, DR, external) and how much it matters (weight 0 to 3).
   Written from the dungeon journal; edit freely, and the dashboard lists any boss casts the file doesn't know about.
3. **Cooldown kinds**: every entry in `cooldowns.toml` has a `kind`. Absorbs never get a DR, channelled damage gets a DR
   first, DoTs prefer sustained healing.
4. **Assignment**: mechanics are covered in order of weight then damage. Weight 3 gets two covers of different kinds,
   weight 2 gets one. Every cooldown keeps to its own timer for the whole fight. Among candidates of the right kind, the
   one the kill logs actually used at that moment wins. Majors that would otherwise go unused are added to the heaviest
   mechanic that can still take one. Only abilities your healers are seen casting are planned, so talent choices
   (Revival vs Restoral) are respected.

The dashboard shows the plan as a table with the evidence, a one-line-per-mechanic team raid note, and the NSRT
personal notes can be generated from the plan (default) or from the consensus of the kills.

## What the dashboard shows

- **Timeline**: consensus cooldown timings per healer over the averaged raid damage curve. Damage spikes are
  labelled with the boss ability responsible. Hollow markers clash with the ability's cooldown and are kept off notes.
- **Raid notes** (MRT / Liquid / Northern Sky) and **NSRT dynamic timer notes** per healer, with tick boxes to choose
  which cooldowns go on. **Plan B** under the NSRT note is one real player's exact sequence from the best-matching kill.
- **Our last pulls vs the plan**: for each planned timing, whether our healer pressed it on time, late, early, or not at
  all, and which major cooldowns were sitting ready when we wiped. This is the section to read after a prog night.
- **Detail slider** (top right): how many kills must agree before a timing counts.

## Running it every night automatically

Double-click `SCHEDULE NIGHTLY.bat` once. It registers a Windows scheduled task that runs the tool at 23:30 every day
(edit the time at the top of the file if you want) and refreshes `out/dashboard.html` silently, logging to
`out/last-run.log`. Your PC needs to be on at that time. Remove it with
`schtasks /Delete /TN "Healer Cooldown Planner" /F`.

## Tuning

- `cooldowns.toml`: which abilities count, their cooldown length, and whether they are `major` (on the note)
  or `minor` (analysed, shown in the table, kept off the note). Add or remove freely.
- `[guild] compare_pulls`: how many of your own recent pulls to compare against the plan (default 6, 0 to skip).
- `[matching]`: raise `candidates_per_spec` if you have an unusual comp and few kills match; set `regions = ["EU"]`
  if you only want EU kills; set `target_duration` (seconds) if you know roughly how long your kill will be.
- `[analysis] min_support`: 0.4 means a timing needs 40% of the analysed kills to agree. Lower it to see more
  speculative timings, raise it for only the rock-solid ones.
- `[output.names]`: override the name printed on the note for a spec.

## Known limits

- Client credentials only read public logs. If your guild's logs go private the "your comp" step will find
  nothing; you can still run with the demo comp logic swapped for a hand-typed list (ask me and I'll add a
  `--healers` flag).
- Phase-relative timings depend on Warcraft Logs having phase data for the boss. Early in a tier that can be
  missing, in which case the tool falls back to absolute timers and says so on the dashboard.
- Kill logs are from guilds that have already killed it, so their pulls are cleaner than prog pulls. Treat the
  timings as the plan for a good pull, not a promise.

## Running the tests

    pip install pytest
    python -m pytest tests
