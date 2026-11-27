# RAG design on the knowledge graph

This note records the decisions for the retrieval system built on the knowledge graph
(docs/db_schematics.md). We build it step by step. Each step is agreed and validated before
the next one starts. The first attempt (commits 4945497 and 7009218) was reverted in 7a61ccf.
Its leftovers are listed in "Inventory" and will be reused only where this design calls for
them.

## Decisions (2026-11-25)

| Stage | Decision |
| --- | --- |
| 1. Community detection | None. The graph's existing groupings are the communities: titles, characters, teams, universes, realities, phases, sagas and series. |
| 2. Summaries | Titles have their Wikipedia plot summaries (per episode for series). We write summaries for the groupings that have none. See "Summaries" for what, how and how they are checked. |
| 3. Indexing | Index everything that retrieval can use, so retrieval is fast. Embeddings use OpenRouter's `openai/text-embedding-3-small` (EMBEDDING_MODEL in .env, 1,536 dimensions). |
| 4. Retrieval | The user picks the strategy by the level of detail they want: local (the default), global or DRIFT. Counting and aggregation questions use a small tool that runs aggregation queries on the retrieved data. |
| 5. Answer style | Later, once retrieval gives good results in good time. Then we compare the strategies. |

## Summaries (agreed 2026-11-25)

### What gets a summary

The raw plots are too big to write group summaries from. Phase Four's titles hold 112,000
characters of plot, the MCU universe's 305,000, and Agents of S.H.I.E.L.D. alone 141,000.
So the summaries are built in three levels. Each group is written from the summaries one
level down (agreed 2026-11-25):

| Level | Summary | Count | Written from |
| --- | --- | --- | --- |
| 1 | Title digests | 98 | the title's plot: the film's text, or a series' episode summaries |
| 1 | Main characters: at least 5 plot facts, or 3 titles and at least 1 plot fact | 374 | the profile, then the plot facts with their evidence sentences, in release order (on average 12 facts; Coulson has the most, 81) |
| 1 | Teams with at least 1 plot fact (all but the Defenders) | 11 | members with role, status and reality (MEMBER_OF), plus the team's plot facts |
| 2 | Series: titles joined by FOLLOWS, film series included (the Iron Man trilogy, the five Avengers films, Loki's two seasons) | 18 | their title digests |
| 2 | Phases | 6 | their title digests |
| 2 | Universes | 10 | their title digests |
| 3 | Sagas | 2 | their phase summaries |
| 3 | Realities that span several universes: Earth-616 (MCU, MCU animation, Netflix, Marvel TV, ABC) and Earth-10005 (Fox X-Men, plus its MCU titles) | 2 | the summaries of their universes; or, for a universe only partly in the reality, the digests of its titles there |

In all, about 540 summaries. Title digests also give global search a level per title,
next to the long plot passages.

Every character, all 2,511, also gets a **profile** built from the graph without an LLM.
This makes every character searchable, and a profile can't hold anything the graph doesn't.
Of the 2,511, 1,571 have no plot fact.

Profiles (built 2026-11-25 by `src/graph/profiles.py`):

- One line per field: name and reality, aliases, species, actors (with how many titles, and
  the TMDB credits when several actors or a voice play the character),
  appearances in release order, wiki team memberships (roles and status), and variants with
  their reality and up to three titles. Empty fields are left out.
- Plot facts are left out of profiles. The written summaries cover them.
- Stored as `Character.profile`. A profile is rebuilt in seconds from the graph, so it has no
  cache file. Run `src.graph.profiles` after `src.graph.load_neo4j`.
- Profiles are 180 characters on average, 973 at most.
- Known noise, fixed with the separate alias task: stale wiki aliases (T'Challa lists Shuri,
  Natasha lists Yelena Belova), and 227 aliases that repeat the label with a wiki suffix
  ("Wanda Maximoff (Marvel Cinematic Universe)").

### What a summary contains

- 150 to 250 words of prose, plus a list of key facts. Each key fact cites its title (and
  the episode for a series), like `[Q107185252 ep 6]`.
- Only what the input says. No outside knowledge.
- A group summary is built from the level below it. A phase is written from its titles' plots,
  and a saga from its phases.

### Output format and prompts (agreed 2026-11-25)

- The writer follows `src/graph/summary_prompt.md`. Its output goes to
  `processed_data/summaries/outputs/<kind>/<id>.json` and holds `kind`, `id`, `name` and
  `input_hash` (copied from the input), `summary`, `key_facts` (3 to 10, each a `fact` with its
  `cite`) and `writer`.
- A summary is 150 to 250 words of prose. A thin input may give less, down to about 30 words.
  It has 1 to 10 key facts, as many as the input really has. The writer never pads: no fact
  restated or split into several. Every key fact is stated in the summary too. (Changed after
  wave 1 from at least 60 words and 3 key facts: those minimums made writers pad thin inputs.
  Yusuf Khan's single plot fact became three key facts.)
- An input with no plot fact gets no written summary. That covers 17 characters (Flash
  Thompson, Stan Lee's cameo character, Dum Dum Dugan, ...) and the Defenders. A summary would
  only restate the profile, and its key facts would have nothing to cite. The profile and the
  graph's members remain.
- Citations are copied from the input. A group summary carries up the title citations found in
  the key facts of the summaries below it, so every key fact leads back to a title.
- The checker follows `src/graph/summary_check_prompt.md`. Its output goes to
  `processed_data/summaries/checks/<kind>/<id>.json`: each statement of the summary and each
  key fact, marked supported or not with a reason, and a `verdict` of pass or fail.
- The automatic check is `src/graph/check_summaries.py`. It checks the JSON shape, that `kind`,
  `id`, `name` and `input_hash` match the input, the length, and the key facts (3 to 10, each
  citing citations that appear in the input). It also lists capitalized names that the input
  never mentions; this is a warning to review, not a failure. The writer runs it on its own
  output and fixes problems until there are none.
- One summary flows: writer, then the automatic check, then the checker. On a fail, the writer
  rewrites from the checker's reasons and the checks run again. A summary is kept once **two
  checks in a row**, each by a new checker, pass it, since checkers vary and one may miss what
  another finds. After two failed rewrites, the summary is flagged for the user's review.

- **Titles stay close to the plot's wording (agreed 2026-11-26).** Of the first 11 title
  digests, 6 failed their first check, against about 15% of character summaries. The writers'
  own knowledge of the films leaked in: Secret Invasion's square became "Moscow", "plans to
  lure" became "lures", "injured while protecting him from a lion" became "injured by a lion".
  So title and season writers add no place, name, cause or outcome the plot doesn't state, and
  keep who does what to whom exactly as the plot says. Checkers compare each event's actors,
  object and outcome with its plot sentence.
- **Plot facts in story order (agreed 2026-11-26).** Within one film, a character's plot facts
  had been sorted by relation type, not by when they happen. So the kept Thor summary had him
  defeat Surtur after reaching Sakaar, where the film has it first. The checkers couldn't catch
  this, since the order matched the input. Now each title's facts are sorted by where their
  evidence sentence appears in the title's plot; a series is sorted by episode first. All 3,552
  evidence sentences are found in their plots, and a test keeps it so. This changed every
  character and team input, so all 385 of those summaries were written and checked again
  (wave 9 onward). Titles and seasons were unaffected.
- **Episodes by number only (agreed 2026-11-27).** Writers kept calling an episode "the last"
  or "the final" one, or wrote "in the end", when the input gives only episode numbers (Gravik,
  Karli Morgenthau, Arthur Harrow, Harold Meachum). Writers now name an episode by its number or
  title, and checkers mark such phrases unsupported.
- **Known limitation: release order for long series.** Plot facts are sorted by their title's
  first release, so all seven seasons of Agents of S.H.I.E.L.D. (2013 to 2020) come before the
  films released after 2013. A team's facts "in order" are therefore not quite chronological.
- **Teams say who leads and when (agreed 2026-11-26).** A team summary gives each leader and
  member once, with the status the member list gives ("Cyclops, a former leader and a current
  member"). It tells leadership changes from the plot facts in order, naming the title. It
  never gives two leaders without saying which is current or in which title. The first X-Men
  '97 draft said the team was "led by Professor X" and then "Magneto leads the X-Men". The 10
  team drafts written before this rule were written again.
- **Reviews (agreed 2026-11-26).** The user, or the main session, can send any summary back with
  a review (`processed_data/summaries/reviews/<kind>/<id>.json`, a failing check in the same
  shape), even one already kept. Two checks can both miss an error: wave 3 kept "is consoled
  by her angrily", where the input has Fisk angry.

### Pilot (2026-11-26)

Five summaries: Iron Man, Agents of S.H.I.E.L.D. season 1, Loki (Earth-616), Dreykov (5 facts)
and the Avengers.

- **The first drafts fail often.** Four of the five failed their first check, on 1 to 3 of 19
  to 38 statements. Every error was a plausible detail the input doesn't give: a timing ("while"
  demonstrating, not after), a place (Sokovia), an order of events, an inferred purpose ("help
  defend Vision"), a dropped hedge ("apparently"), or a key fact citing the wrong episode. All
  five passed after at most two rewrites.
- **Checkers vary.** A new checker sometimes found an issue an earlier one missed. Hence the
  rule of two passing checks in a row.
- **Fixes made after the pilot:**
  - The writer tells the story and never talks about the input ("the input notes", "is
    recorded as", "in one plot fact"). The checker marks such sentences unsupported. A death
    undone later takes one sentence.
  - Each membership role keeps its own status, in profiles and team inputs:
    `founder (current), leader (former)`. Before, `founder, leader; current, former` lost
    which status went with which role.
  - The name check no longer joins neighbouring known names into one unknown name (a
    possessive, a bracket, a title next to a name), and it ignores quotes in the input
    (James "Rhodey" Rhodes).
- **Facts joined with outside knowledge.** The Avengers summary failed again after the fixes:
  it placed a battle in Sokovia, and had the Wakandans fight "to defend Vision". The second
  error passed both checkers. A team's input is single-sentence facts from many films, cited
  by ID only, so the writer filled the gaps from what it knows of the films. Three changes:
  - Fact lines name their title.
  - The writer joins facts only with what the input says, and tells facts from different
    titles title by title.
  - The checker looks hardest at the words that join two facts: places, purposes, causes
    and order.
- **Round 2 (after these changes):** the Avengers, Loki and Dreykov summaries were written again
  from their new inputs. All three passed two checks in a row on the first draft. The
  Avengers summary now goes title by title, with no added place or purpose. So all five pilot
  summaries are kept. Iron Man and Agents of S.H.I.E.L.D. season 1 needed no new round, since
  their inputs didn't change.
- **Wave 2 (first checks of 153 wave-1 summaries):** 129 passed (84%) and 24 failed. The
  causes:
  - about 11 paired an actor with a role the input didn't state ("Lily Chee as young Elektra",
    "voiced by Cal Dodd");
  - about 7 filled in who acts in a fragment ("learn that Eleanor killed Armand" became
    "Barton and Kate learn...");
  - about 5 joined facts with an order or a link the input lacks;
  - 1 talked about the input.

  Three changes followed:
  - **Credited roles in profiles.** Where a character has several actors or a voice role, the
    profile gives each actor's TMDB credit (`PLAYS.credited_as`): `Toby Nichols (1 title, as
    "Young Danny Rand")`. This changed the input of 119 of the 374 main characters, and their
    55 written summaries were written again.
  - **Writers don't fill in a fragment.** Who acts is named only when the fact names them.
  - **Checkers mark a doubtful statement unsupported.** Three checkers had passed statements
    they called borderline.
- **Data problem found and fixed: plot facts linked across realities.** A What If...? fact
  (Multiverse) was linked to `Avengers@Earth-616`, so the summary said Ultron defeats the
  Earth-616 Avengers. The extraction agents chose team IDs from one list for every title.
  - Of the 56 plot-fact ends linked to a node of another reality than their title's, all 38
    character links are right: each character appears in that title (the Raimi and Webb
    characters in No Way Home). So are 14 of the 19 team links: one of the team's members
    appears in the title (the Earth-838 Illuminati in Multiverse of Madness, the Earth-828
    Fantastic Four in Doomsday).
  - The other 5 are all What If...? facts linked to the Earth-616 Avengers, HYDRA and
    S.H.I.E.L.D.
  - The rule (in `src/graph/load_neo4j.py`): a team linked from another reality counts only when
    one of its wiki members appears in the title. Otherwise the end is resolved as an unlinked
    name: a team of that name in the title's reality, else a Thing. A test in
    `tests/neo4j/test_graph.py` keeps it so. The graph evaluation is unchanged (39 PASS).
  - Rebuilding the graph removed the leftover plot passages from Neo4j. Their vectors stay
    cached, and the indexing step loads them again.
- Pilot set: Iron Man (a film), Agents of S.H.I.E.L.D. season 1, Loki (Earth-616, many facts),
  a main character near the threshold (5 facts), and the Avengers.

### Who writes and checks them

Claude Code subagents on Sonnet 5.5 write the summaries, the same way the plot facts were
extracted (docs/extraction_agents.md). The OpenRouter models are not used. Each summary is
checked three ways:

1. **Automatic**: every key fact cites a title that is in the input, and every name in the
   summary exists in the input.
2. **A second subagent**: a separate Sonnet 5.5 subagent compares each statement with the
   input facts and lists anything unsupported. A summary with unsupported statements is
   rewritten or flagged.
3. **The user**: reviews a sample of about 10 summaries across the kinds, including the
   expert decisions (for example, Captain Carter is a separate character from Peggy Carter).

### Inputs

Each summary gets an input file that holds exactly what its subagent may use (built by
`src/graph/summary_inputs.py`):

```
processed_data/summaries/
  inputs/<kind>/<id>.json    id, kind, name, level, sources, the input text, input_hash
                             (sources: the plot's title qids, or for a group [kind, id] of each member summary)
  outputs/<kind>/<id>.json   written by the subagents: summary, key facts, input_hash, writer
  checks/<kind>/<id>.check1.json, .check2.json   the two checks of the current version
  status.json                every summary's state and the batches per next action (src/graph/summary_status.py)
```

- The kinds are `title`, `season`, `character`, `team`, `series`, `phase`, `universe`, `saga`
  and `reality`.
- A summary is pending when its output is missing, or the output's `input_hash` differs from
  its input's. An input file is rewritten only when its content changes, the same rule as
  `prepare_extraction` uses.
- A level 2 or 3 input can be built only once the summaries below it exist. So the builder
  builds what it can, and runs again after each level is written. An upper input contains
  the lower summaries' text, so a rewritten title digest makes its phase pending again.
- Citations in inputs are `[<title qid>]`, or `[<title qid> ep <n>]` for a series episode.
  A character fact looks like
  `[Q107185252 ep 6] Loki, season 1: Sylvie KILLS He Who Remains: "Sylvie kills He Who Remains, ..."`.
  It names its title, so the writer need not guess which film a citation is.
- An input over 40,000 characters is reported, not cut. Two rules keep inputs under the
  limit (agreed 2026-11-25):
  - **A title too long for one input is split by season.** Each season gets a digest
    (kind `season`, id `<title qid>-s<n>`), and the title digest is written from its season
    digests. This applies to Agents of S.H.I.E.L.D., Jessica Jones and Daredevil, about 13
    seasons in all.
  - **A group whose digests exceed the limit is built from the level that covers it.** A
    universe is written from the summaries of the phases its titles are in, plus the digests
    of its titles in no phase. The input notes which titles of those phases belong to other
    universes. A reality is written from its universes' summaries, each taken whole, and the
    input notes which of their titles belong to other realities. This applies to the MCU
    universe (58 titles) and Earth-616, whose inputs from digests would come to about 87,000
    and 90,000 characters.

Built 2026-11-25. Ready now: 95 title, 13 season, 391 character and 12 team inputs, 511
pending in 30 batches, none over the limit. Agents of S.H.I.E.L.D. (7 seasons), Daredevil
and Jessica Jones (3 each) are split by season, and their 3 title digests wait for their
seasons. The 38 inputs at levels 2 and 3 also wait for the summaries below them.

The MCU universe is only partly in Earth-616 (Deadpool & Wolverine is Earth-10005), and Fox
X-Men is only partly in Earth-10005 (Logan is Earth-17315). So each of those realities is
written from title digests, apart from the universes that lie wholly in it. If that comes to
more than the limit, the reality is written from its universes instead (see the rules above).

Validation: unit tests on the hash, the pending rule, the cascade and the character
threshold. On the real inputs, check the counts, that every citation names a real title
(and a real episode), that Phase One holds exactly its six titles, and the 40,000-character
limit.

### Run result (2026-11-27)

All 534 summaries are written and kept. Levels by kind:
- level 1: 374 characters, 98 titles, 13 seasons, 11 teams;
- level 2: 18 series, 6 phases, 10 universes;
- level 3: 2 sagas, 2 realities.

The run took 49 waves.

Eight summaries were flagged after their last allowed rewrite: Shuri, the Earth-92131 X-Men, Wonder Man, Your Friendly Neighborhood Spider-Man, Agent Carter, X-Men: First Class, The Punisher and Phase Four.
- The main session fixed each one by hand, taking the wording from the input (agreed 2026-11-27).
- A hand fix makes the summary's old checks stale, so it goes back to check 1 and is kept only after two new passing checks, like any other summary.

Problems found during the run:
- **Lumped checks.** Some checkers marked a range of key facts as supported in one statement ("Key facts 1-5 match") instead of checking each one. The 45 such passes were deleted and redone, and the checker prompts now forbid lumping. The status script's count rule (at least as many statements as key facts) misses this, because the summary's own sentences already reach that count.
- **Group inputs.** The headings in group inputs don't carry each title's medium, year, universe or reality. A group summary may state these for a title only where that title's own summary does.

### Storage and updates

- The source of truth is files in `processed_data/summaries/`, one per summary. Each holds the
  text, the key facts, the sources, the writer and a hash of the input. Reloading the graph
  clears the database, but these files survive, so nothing is written twice.
- In Neo4j, each summary becomes a `Summary` node linked to what it describes. Phases, sagas
  and universes have no node of their own, so their summary links to its member titles.
- A summary is rewritten only when the hash of its input changes (the project's
  only-redo-what-changed rule).

### Summary nodes (agreed 2026-11-26)

Loaded by `src/graph/load_summaries.py`, run after `load_neo4j`, `profiles` and `summary_inputs`.

- **Node:** `(:Summary {id: "<kind>:<id>", kind, level, name, text, key_facts, key_fact_cites,
  input_hash, writer})`. Neo4j properties can't hold maps, so the key facts are two lists of
  the same length: the sentences and their citations. A unique constraint is on `id`.
- **SUMMARIZES** links a summary to what it describes: its Title, Character or Team; a season to
  its series' Title, with a `season` number; a series, phase, universe, saga or reality to every
  Title it covers, through the summaries it was written from (a saga reaches its titles through
  its phases).
- **PART_OF** links each summary a group was written from to the group's summary (title -> series,
  title -> phase -> saga, season -> title, universe -> reality), so DRIFT search can step from a
  broad summary down to narrower ones. Character and team summaries have none.
- Group inputs record their members as `[kind, id]`: an id alone is ambiguous (a series is named
  by its first title's qid, so `Q106182` is both the X-Men title and the X-Men series).
- The load stops, naming them, unless every summary is kept against its current input. It
  replaces all Summary nodes rather than merging them, so a summary that no longer exists can't
  linger, and running it twice changes nothing.
- The keyword and vector indexes on summaries belong to the index step.

Result (2026-11-26): 534 Summary nodes, 864 SUMMARIZES and 205 PART_OF links; the same counts
after a second run. Validation (`tests/neo4j/test_summaries.py`): one node per summary input and
kind; every summary has a SUMMARIZES link; each title, character and team summary points at its
own node and every Title has a title summary; Phase One links to its 6 titles and the Infinity
Saga to all its titles; each season link carries its number; every title summary reaches its
universe's summary through PART_OF; every key-fact citation names a real title and episode.

## How we judge retrieval

We judge retrieval on its own, before any answer is written. For each strategy and each
evaluation question (docs/evaluation_questions.md) we measure:

- **quality**: does the retrieved data contain the facts the expected answer rests on?
- **speed**: how long does retrieval take?

### How it is judged (agreed 2026-11-27)

- **Quality is judged by subagents, not by Python.** Matching strings can't tell a stated fact
  from a passing mention, so Claude Code subagents on Sonnet 5.5 compare each retrieved context
  with the expected answer (rules: `src/retrieval/judge_prompt.md`; runbook:
  `docs/retrieval_agents.md`). A judge splits the expected answer into its items and marks each
  `yes`, `partly` or `no` with the context line it rests on. A count or "the most" is `yes` only
  if the context gives the whole set. It also lists context lines that contradict the answer.
  The verdict is `complete` (every item yes), `partial` or `missing`.
- **Two judges per question (agreed 2026-11-27).** One judge changed two verdicts between local
  runs 1 and 2 on the same evidence, so each question now gets two independent judges; the lower
  verdict counts, and the report lists where they disagree.
- **Python runs and times.** `src/retrieval/evaluation.py` runs a strategy on the 50 questions,
  saves each context with its retrieval time, and batches the contexts for the judges; `report`
  collects verdicts and timings into a report. The question vectors are embedded first,
  through the cache, and timed apart, so a strategy's time is the retrieval alone.
- **No LLM inside retrieval.** Retrieval finds its entry points with the name index and vector
  search on the question, then walks the graph. The only model call is the question's
  embedding. The LLM is left to the answer step.
- **Sub-steps:** R1 the judging (this), R2 local search, R3 global search, R4 DRIFT, R5 the
  aggregation tool. Each is reported and agreed before the next.
- **Calibration (2026-11-27).** Two judges each scored the same eight contexts built from the
  graph, without being told the verdicts expected. Both gave the expected verdict in all eight:
  Captain Marvel's header alone (complete); Iron Man's header and Sylvie's profile (missing); the
  header with 1996 planted (missing, and both quoted the conflict); all 66 films with their
  directors for "who directed the most" (complete); only the Russo and Raimi films (partial,
  "set may be incomplete"); Iron Man's summary for the Blip question (missing); the Captain
  Marvel header among unrelated text (complete). The judgement call, Endgame's summary for how
  the Blip was reversed, was complete for both: they took "Banner uses the gauntlet to undo
  Thanos's disintegrations" as his snap, and one said so in its note. Judges split items
  somewhat coarsely (the Russos' five films as one item), which the report shows per question.

## Local search (R2, agreed 2026-11-27)

`src/retrieval/local.py`, no LLM; the strategy `local` of `src/retrieval/evaluation.py`.

- **Entry points:** names and aliases from the name index, and the group summaries' names, that
  occur in the question as a whole phrase with the same capitals (a hyphen joins words; "The X"
  also matches "the X" with the span of X; a one-word match at the question's start is
  skipped). The longest overlapping match wins; every entity sharing it is kept (variants).
- **One step from each:** a title's header, summary, crew and every character with its actor; a
  character's profile, summary and who plays each of its variants; a person's roles and crew
  credits; a team's wiki members and summary; a group's summary and its titles (release and
  in-universe years and order, universe, phases; money and ratings are left to the aggregation
  tool); titles, characters, teams and things add their 8 plot facts closest to the question.
- **Search:** plot facts (12), passages (3) and summaries (3), keyword and vector rankings fused
  by reciprocal rank, without what the entry blocks already show.
- **Size:** at most 20,000 characters. Each entry block gets a fair share (an equal share, what a
  shorter block leaves going to the others) and is cut at its own end; 4,000 are kept for the
  search hits. The run warms the database with one untimed call first.

| Run | Complete | Partial | Missing | Local types (34): complete / partial / missing | Retrieval time |
| --- | --- | --- | --- | --- | --- |
| 1 (20261127T165455Z) | 19 | 19 | 12 | 16 / 15 / 3 | median 0.30 s, max 2.40 s (cold start) |
| 2: fair shares, variants' actors, warm-up (20261127T170143Z) | 18 | 19 | 13 | 15 / 16 / 3 | median 0.22 s, max 0.45 s |
| 3: in-universe order restored; two judges, the lower counts (20261127T172908Z) | 19 | 18 | 13 | 16 / 15 / 3 (18 / 14 / 2 by the higher verdict) | median 0.26 s, max 1.95 s |
| 5: the cast's other titles, members' aliases, one per line (20261127T173811Z) | 16 | 19 | 15 | 13 / 17 / 4 | median 0.23 s, max 0.40 s |
| 6: cap 32,000 (20261127T174313Z; 34 judgements carried over from 5) | 19 | 16 | 15 | 16 / 14 / 4 (22 by the higher verdict) | median 0.22 s, max 0.80 s |

The goal (28 of the 34 complete, none missing) is not met. In run 3 the two judges agree on 47
of 50; of the three splits, Q33 is a judge error (judge 1 says Doomsday has no cast list; it
has, with Charles Xavier [Earth-10005]), Q27 a strict reading ("May is short for Maybelle"),
Q02 partial against missing. Run 2 fixed what it aimed at (Q06
variants' actors, Q33 Doomsday's cast no longer pushed out) but its group lines dropped the
in-universe order (Q14; restored since, not yet re-judged), and two verdicts changed on the
same evidence (Q01, Q25): one judge per question is not steady enough to measure a difference
of a few questions. The remaining local gaps: an actor's other titles need a second step (Q05);
facts not shown or not in the graph (Q19 Wikidata's "different from", Q26, Q28, Q30 aliases);
questions that name nothing (Q15, Q16, Q18), for global search and DRIFT; questions over the
whole graph (Q02, Q08, Q11), for the aggregation tool. Q13's judge listed four titles released
after Endgame and set before it that the expected answer leaves out: a point for the expected
answer, not for retrieval.

## Global search, DRIFT and the aggregation tool (R3 to R5, built 2026-11-27)

The user asked to finish every retrieval sub-step in one go (2026-11-27), so these were designed
and built without a stop between them; the choices below are recorded for review. None uses an
LLM: the only model call is the question's embedding.

- **Global search** (`src/retrieval/global_search.py`, strategy `global`): the summaries of what
  the question names (a title, main character, team or group, matched as in local search), then
  the summaries found by the keyword and vector indexes, fused; at most 10, each with its key
  facts and citations, a group's also with its titles. Same cap and fair shares as local.
- **DRIFT** (`src/retrieval/drift.py`, strategy `drift`): a primer of at most 2 group summaries
  (named, else the first level-2 or level-3 hits), then PART_OF steps down, keeping the 3
  children closest to the question at each level, until the titles (at most 6); for each title
  reached, its 6 plot facts and its plot passage closest to the question. A named title starts
  there. Microsoft's DRIFT asks an LLM for follow-up questions; here the steps follow the
  summary hierarchy, ranked by the question's vector.
- **The aggregation tool** (`src/retrieval/aggregate.py`, strategy `aggregate`): 11 fixed views
  over the whole graph (box office with the previous title in its series, budget, TMDB ratings,
  average rating per phase, in-universe timeline, titles per phase, characters by titles,
  actors by titles with cameos, characters by co-stars in films, directors by films, actors who
  play two or more different characters). The question's vector picks the 2 views whose
  descriptions are closest. Each view's header says it is computed over all titles,
  characters or people, so a "the most" or a count rests on the complete set. This answers the
  open point on aggregation: the tool doesn't count retrieved data, it queries the whole graph.
- **What each is judged on** (to keep the judging proportionate; can be widened to all 50):
  global and DRIFT on the big-picture questions (Q35 to Q40) and the plot questions that name
  nothing or need a wide view (Q15 to Q18, Q34); the aggregation tool on the 14 questions over
  the whole graph (Q02, Q08, Q11, Q38, Q39, Q41 to Q48, Q50).
- **Local search, final (run 6):** the cap was raised to 32,000 characters (6,000 kept for the
  search hits) after runs 2 to 5 showed 20,000 cutting questions that name several entities
  (Q07's Endgame cast, Q17's Endgame hits, Q29's Avengers members, Q32's Doomsday cast). A
  title's cast lists each actor's other titles on the actor's own line, and a team's members
  their aliases, one per line, so a cut drops the lowest billed or last members, not a whole
  list. `evaluation carry` copies a previous run's judgements where the context is the same, so
  only changed questions are judged again.

### Final runs (2026-11-27)

After the runs above, cuts fall at the last line or sentence end (a summary is one long line, so
cutting at line ends alone dropped all of it), and DRIFT keeps 3 summaries per step in all (3
per parent spread 2 sagas over 18 titles and cut every summary to its heading). Verdicts are the
lower of two judges; judgements are carried over where a context didn't change.

| Strategy (run) | Judged on | Complete | Partial | Missing | Retrieval time |
| --- | --- | --- | --- | --- | --- |
| local (local/20261127T175130Z) | all 50 | 20 | 15 | 15 | median 0.24 s, max 0.41 s |
| local, the 34 local-type questions | 34 | 17 | 13 | 4 | |
| global (global/20261127T175144Z) | 11 | 3 | 8 | 0 | median 0.13 s, max 0.24 s |
| DRIFT (drift/20261127T175147Z) | 11 | 2 | 7 | 2 | median 0.32 s, max 0.36 s |
| aggregation (aggregate/20261127T175152Z) | 14 | 8 | 6 | 0 | median 0.04 s, max 0.12 s |

Taking each question's best strategy: 29 of 50 complete, 21 partial, none missing.

- **Aggregation** answers what local can't: Q08, Q11, Q38, Q39, Q41, Q42, Q47 and Q50 complete.
  Its partials: Q02 (Peter Dinklage's Eitri is a one-title, non-main character), Q43 (Black
  Panther: Wakanda Forever has no FOLLOWS link to Black Panther, a data gap), Q44 to Q46 (the
  expected answers leave Stan Lee's cameo character out; the views show him), Q48 (the expected
  answer calls Phase Three the highest while Phase Six's two films average higher).
- **Global** completes Q35, Q37 and Q38 and is never missing on its 11; DRIFT completes Q17 and
  Q35. Neither finds the nameless Q15 ("how long after the snap"): the summary and fact
  searches don't reach Endgame from that wording. Q16, Q18, Q36 and Q40 stay partial with every
  strategy: the missing items are a motive (overpopulation), No Way Home's spell, Steve Rogers
  retiring, and Doom's actor.
- **Open for the user:** whether to widen the judging of global and DRIFT to all 50; the
  expected answers that rest on wording or on sources the graph doesn't hold (see Local search);
  and the 32,000-character cap, raised during this step.

## The answer step (stage 5, agreed 2026-11-27)

- **Model:** QA_MODEL in .env (`openai/gpt-6-luna`) through OpenRouter, the client the
  embeddings use. Temperature 0.
- **Input:** the context of the strategy the user picked (local, global or DRIFT) and the
  question. The rules are in `src/retrieval/answer_prompt.md`: answer only from the context and
  the views, say what the data doesn't give, give full lists, keep realities apart.
- **The aggregation tool is a tool the model calls.** It gets one function, `aggregate(view)`,
  whose description lists the 11 views; a call returns that view's block over the whole graph.
  The model is told to call it for counts, rankings, "the most" and averages instead of counting
  from the context. At most 2 rounds of calls; after that the model must answer.
- **Comparison:** all 50 questions with each of local, global and DRIFT (150 answers). Each
  answer is judged by two Sonnet 5.5 subagents against the expected answer
  (`src/retrieval/answer_judge_prompt.md`), the lower verdict counting, as for retrieval. The
  judges see the answer and the expected answer, not the context: a miss is traced afterwards to
  retrieval (its verdict on the same context) or to the answer step.
- **Validation:** unit tests for the chat call (the key and the messages never in an error), the
  tool loop (a view call, an unknown view, the forced last round) and the answer runs (saved,
  carried, reported); a smoke run of three questions (Q12, Q08, Q35) read by hand before the
  full run; then the full run. The measure: how many answers lose what their context held (the
  retrieval verdict was complete, the answer's isn't), and whether the 14 whole-graph questions
  reach at least the aggregation tool's 8 complete through the tool. Answer time is reported
  per question, apart from retrieval time.

### First answer runs (2026-11-27)

Two judges per answer, the lower verdict counting; the judges disagree on 2, 1 and 1 questions.

| Strategy (run under eval/answers/) | Complete | Partial | Missing | Answer time |
| --- | --- | --- | --- | --- |
| local (local/20261127T190551Z) | 19 | 28 | 3 | median 2.3 s, max 21.2 s |
| global (global/20261127T190553Z) | 9 | 35 | 6 | median 2.6 s, max 14.1 s |
| DRIFT (drift/20261127T190555Z) | 6 | 30 | 14 | median 2.6 s, max 21.7 s |

Retrieval stays under 0.6 s; answers over 8 s are the ones that call a large view (timeline,
box office, actors with two characters) or write a long list. Local leads on every question
type; taking the best strategy per question gives 21 complete, 28 partial and 1 missing.

- **The tool works:** the model called a view on every whole-graph question, and the right one.
  Local answers gain on 13 questions over local retrieval (Q39, Q41, Q47, Q48 now complete), but
  only 4 of the 14 whole-graph questions are complete, against the aggregation tool's 8.
- **Lost by the answer step** (local retrieval complete, the answer not): Q03 (Wanda's variants
  left out), Q07 (Cassie Lang dropped), Q23 (Doomsday and the X-Men '97 variant left out), Q32
  (Reed as leader), Q34 (says Gamora rejoined, a misreading), Q35 (What If...? and I Am Groot
  continuing into Phase Five).
- **Why:** the answers are short and answer the question narrowly, while the expected answers
  add the details around it: the runners-up of a "the most" (Q08, Q50), the earliest film after
  the earliest title (Q11), the titles in two phases (Q38). Two are misreadings (Q34; Q42, The
  Incredible Hulk instead of The Marvels as the lowest grossing MCU film). Q44 and Q46 lose
  on Stan Lee's cameo character, which the expected answers leave out and the views show.

### Answer run 2: answer fully (2026-11-27)

The user agreed to widen the answer prompt (rules 3 and 4 of `answer_prompt.md`): check every
list item again, and give the details around the answer the data holds (the runners-up and
ties of a "the most", the top film when the top title isn't one, the earliest film, titles in
two groups, a character's variants, members' roles, other titles). The views and the expected
answers stay as they are; Stan Lee's cameo character is still open. Only 4 answers came out the
same, so 146 were judged again.

| Strategy (run under eval/answers/) | Complete | Partial | Missing | Answer time |
| --- | --- | --- | --- | --- |
| local (local/20261127T192736Z) | 18 (19) | 31 (28) | 1 (3) | median 3.3 s, max 16.0 s |
| global (global/20261127T192739Z) | 13 (9) | 34 (35) | 3 (6) | median 3.1 s, max 18.1 s |
| DRIFT (drift/20261127T192741Z) | 9 (6) | 29 (30) | 12 (14) | median 3.1 s, max 16.5 s |

(Run 1 in brackets.) The best strategy per question gives 21 complete, 29 partial, none
missing. The rules did what they aimed at: Q03, Q08, Q32, Q35, Q38, Q42 and Q46 went up for
local, and 6 of the 14 whole-graph questions are complete (4 before; the aggregation tool's
context, 8). But 6 local answers went down (Q05, Q06, Q10, Q16, Q22, Q29), and the causes are
the model's, not the rules': list items dropped (Thor in Q29, Toby Leonard Moore in Q05, as
Cassie Lang in Q07 before), a detail left out that the first answer had (Q10's ten titles,
Q22's First Steps). With temperature 0 the same context still gives answers that keep
different items, so the answer model drops items from long contexts in both runs.

### Shared characters and members (2026-11-27)

The user ruled out trying a stronger answer model ("a stronger model shouldn't do much
difference"). Tracing the dropped items to the contexts: Q07 asks for the characters in two
casts and Q29 for the members of two teams, so the model has to intersect two long lists, and
in Q29 the Avengers list was cut after 24 of its members (Thor among those left out). So
local search now adds, when a question names two titles or two teams, what they share, worked
out by the graph: "Characters in both casts" or "Characters who are members of both", first in
the context, with each title's QID and each team's reality (the four titles named "Fantastic
Four" otherwise read alike). It shows on 7 questions (Q07, Q17, Q26, Q29, Q31, Q32, Q33);
Q07's block is exactly the expected ten, Q29's Nebula, Rocket and Thor. The other 43 contexts
are unchanged (local/20261127T195339Z). Q05, Q10 and Q22 are not this: the item was in the
context and the answer left it out.

Judged (retrieval local/20261127T195339Z: 20 / 15 / 15 as before, Q07 and Q29 still complete;
answers answers/local/20261127T195439Z): **local answers 26 complete, 23 partial, 1 missing**
(run 2: 18 / 31 / 1). Q07 and Q29 went from partial to complete as aimed; Q17 and Q26 stay
partial, Q31 to Q33 complete. But the other six gains (Q05, Q06, Q09, Q11, Q19, Q22) come
from contexts that didn't change: the QA model at temperature 0 gave the same text for only 1
of the 50 questions, so a rerun alone moves about 6 verdicts (here all up, none down). A
difference of a few questions between two answer runs is within that noise; the shared blocks
account for 2. 7 of the 14 whole-graph questions are complete.

### Cameos (agreed 2026-11-27)

Q44 to Q46 lost on Stan Lee's cameo character: the expected answers leave it out, the views
ranked it first (19 titles, 337 co-stars). The user chose to teach the graph about cameos rather
than change the expected answers: every acting credit of Stan Lee's is a cameo, and a character
with only cameo credits has `cameo: true` (src/graph/load_neo4j.py, CAMEO_PEOPLE; docs/
db_schematics.md). The character views (characters by titles, by co-stars) leave cameo
characters out and say so in their headers; the actors view gives each actor's cameos ("Stan
Lee: 36 titles (36 cameos, 0 not)"). The graph rebuilt (load, profiles, summaries, indexes; no
embedding redone); the views now give Nick Fury 14 and Steve Rogers 12, Stan Lee 36 then
Samuel L. Jackson and Chris Evans 15, Steve Rogers 239, Nick Fury 223 and Thor 201, the expected
answers. The graph-only evaluation (src.graph.evaluate) checks the same through `cameo`.

## The front end (agreed 2026-11-27)

For the MCU expert to test the system himself. The user chose: the case board with cited facts
(the reference: a Heptabase-style case board, "my_plan/D. Case board, Heptabase style@2x.png", not tracked), no
feedback capture in the app, plain HTML/CSS/JS served by Flask (no build step), so it can be
exposed later.

- **Backend:** `src/web/app.py`. `GET /` serves the page; `POST /api/ask` takes the question
  (1 to 500 characters) and the strategy (local, global or DRIFT) and returns the answer, the
  lines it cites, the views called, what the question names, the board and the timings. A
  failure returns a message without the question or the error text; the log keeps the error
  type only. The question is embedded directly, not through the query cache (which keeps only
  the evaluation questions). Run: `python -m src.web.app` (http://127.0.0.1:5000, Flask's own
  server; a production server comes with exposing it).
- **Citations:** the answer step numbers every line of the context and of the views it calls
  ([1], [2], ... across them, headings and cut marks unnumbered), and the prompt (rule 6) asks
  the model to cite the numbers each statement rests on; ranges ([1-3]) are read too. The answer
  comes back with the lines it cites. The answer judges are told to ignore the numbers. The
  answer runs above were made before citations; the next answer run measures them.
- **The board** (`src/retrieval/board.py`, no LLM): cards for every entity the question names
  (variants included), then one per name the answer names (citations and italics taken out
  first; the answer's first word counts, unlike a question's), 24 at most; an answer's thing
  (place, universe, object) with no link to the others is left out. Links: the graph's relationships between two cards
  (not ACTED_IN, which repeats PLAYS), one per direction and kind, plot (red) or data (grey), its
  label naming every type it stands for, its evidence the plot quote, the cast credit, the wiki
  role or the Wikidata shared identity. Groups (phases, sagas) are summaries, not cards.
- **The page** (`src/web/static`): left, example questions, the level of detail, the question,
  "How it got there" (strategy, what was named, views, lines cited, times) and the answer with
  one badge per citation; middle, the board (Cytoscape.js 3.30.2 for layout, pan and zoom, with
  HTML cards over its nodes); right, the evidence of the selected card or link, and the cited
  lines, which a badge lights up.
- **Checked:** unit tests for the numbering, citations with ranges, the board's choices, links
  and evidence, and the endpoints (bad requests, failures without the question); in the browser,
  four questions across local and global, citation badges and the console. Found and fixed on
  the way: the board read "24-29" in a citation as X-24; italics hid "Loki, season 1"; the
  answer's first word was skipped like a question's; parallel links stacked their labels.
- **Server and page tests (2026-11-27):** `tests/neo4j/test_web.py` runs `/api/ask` end to end
  on the loaded graph with a fake model (every strategy answers from numbered lines and returns
  the cited ones; the board shows Captain Carter's variants with their Wikidata identity and
  cast credits; a view call is numbered on from the context; a question naming nothing still
  answers). A live run with the real model (10 questions over the three strategies, a French
  question with quotes and HTML, an off-topic one, bad requests): every citation names a real
  line, answers in 2 to 10 s, bad requests 400, wrong method 405. In the browser: strategy
  switch, typed question with Enter, card and link evidence, fit, citation badges, a phone-width
  layout, HTML in answers and evidence shown as text, a clean console. Fixed on the way: the
  network error showed the browser's "Failed to fetch" and left the last board up (now a plain
  message, and each question clears the board and evidence first); a list under an intro line
  rendered as plain lines; the Ask button and the legend were cut off at phone width; one name
  the answer used put every entity with that alias on the board (Okoye, Ingrid for "Black
  Widow"): the board now takes one entity per matched phrase, the one whose own name it is,
  a person before a character of that name; the actors of a ranking were dropped as unlinked
  (now only unlinked things are).

## Inventory (checked 2026-11-25, read-only)

### Nodes

| Label | Count | Names to search | Text to embed | Other properties (how many have a value) |
| --- | --- | --- | --- | --- |
| Title | 98 | `title` | plot summary, as Passages (all 98 titles) | type, universe, reality, tier, year, first_release_date and release_order (98); phases and sagas (61 in a phase); chronological_order, start_year and end_year (69); runtime_minutes (87); box_office_usd and budget_usd (65); tmdb_rating and tmdb_votes (98) |
| Character | 2,511 | `label` + `aliases` (5,976 aliases) | none | reality, base_qid (2,511); species (2,131); mcu_wiki_page (2,216); marvel_db_page (284) |
| Person | 7,599 | `name` | none | tmdb_id (7,423); qid (3,897); birth_date (2,752) |
| Team | 12 | `name` + `aliases` (8 have aliases) | none | kind, reality |
| Thing | 691 | `name` | none | type, reality |
| Passage | 738 | `heading` | `text` (whole paragraphs, up to about 1,500 characters) | title_qid, episodes; already embedded with text-embedding-3-small (left over from the first attempt) |

### Relationships

| Type | Count | Properties | Text |
| --- | --- | --- | --- |
| APPEARS_IN (Character → Title) | 3,285 | | |
| PLAYS (Person → Character) | 3,407 | title_qid, credited_as, billing_order | |
| ACTED_IN, DIRECTED, WROTE (Person → Title) | 8,889, 112, 205 | | |
| FOLLOWS (Title → Title) | 38 | | |
| VARIANT_OF (from the data) | 197 | shared_qid | |
| MEMBER_OF (from the wikis) | 455 | role, status, source, source_url | |
| 14 plot relations (`source: 'plot'`) | 3,552 | title_qid, episode, evidence, note, chunk | `evidence`: one sentence per fact (about 74 characters on average); `note` on 1,457 facts |
| FROM (Passage → Title) | 738 | | left over from the first attempt |

Either end of a plot fact can be a Character, a Team or a Thing. Most facts join two
Characters, for example 667 ENEMY_OF, 489 ALLY_OF and 365 RESCUES.

### Indexes in Neo4j now

| Index | Kind | On | Note |
| --- | --- | --- | --- |
| title_qid, character_id, person_key, team_id, thing_key | range (unique keys) | the node keys | part of the graph |
| entity_names | full-text | names and aliases of Title, Character, Person, Team, Thing | left over from the first attempt |
| passage_embedding | vector (1,536, cosine) | Passage.embedding | left over |
| passage_text | full-text | Passage.heading, Passage.text | left over |
| passage_id | range | Passage.id | left over |
| actor_key | range | label Actor, which no node has | stale, from an earlier schema; to remove |

No index exists yet on the properties that retrieval filters on (character label and reality,
person name, title name and universe), or on any relationship property.

## Index set (agreed 2026-11-25)

The graph is small (about 11,000 nodes). A label scan takes milliseconds, and walking from a
node to its neighbours needs no index. So nearly all the speed comes from the keyword and
vector indexes, which do the searching. Lookup indexes are kept to the two large labels.

### Lookup (range) indexes

| Index | Used by |
| --- | --- |
| Character `label`, `reality`, `base_qid` | local: exact names, and variants by base_qid; aggregation |
| Person `name` | local; aggregation |

Title, Team and Thing (98, 12 and 691 nodes) get no lookup indexes, and neither do plot-fact
properties: facts are reached by walking from a node. We add one only if timing shows a need.

### Keyword (full-text) indexes

| Index | Used by |
| --- | --- |
| `entity_names`: the names and aliases of every node (exists) | local: the entry point for each name in a question ("Natalie Rushman" is Natasha) |
| `passage_text`: plot passages (exists) | local: the keyword half of plot search |
| Evidence sentences of the plot facts (new; one index over the 14 plot relationship types) | local: finds facts by their words ("snap", "Soul Stone"), even when the question names no entity |
| Summaries (new, once they exist) | global and DRIFT: the keyword half of summary search |

### Vector indexes (text-embedding-3-small, 1,536 dimensions, cosine)

| Index | Used by |
| --- | --- |
| `passage_embedding`: plot passages (exists; the 738 vectors are cached) | local: the paraphrase half of plot search |
| Evidence sentences (new; 3,552 sentences, about 260,000 characters) | local: finds facts by meaning ("who sacrificed themselves") |
| Summaries (new, once they exist, about 450) | global and DRIFT: the paraphrase half of summary search |

Character profiles get no vector index for now. A profile is names, titles and teams, which
the name index already covers. Retrieval still returns profiles as context.

Where something has both a keyword and a vector index (passages, evidence, summaries),
search queries both and fuses the two rankings. That worked best in the first attempt.
The details belong to the retrieval step.

### Cleanup

- Drop `actor_key`, which indexes a label no node has.
- Make the leftover passages and their indexes part of the graph build. FROM
  (Passage → Title) joins the schema, so `test_only_known_relation_types` passes again.

### Validation

- Every index exists and is ONLINE.
- Known lookups return the right node in under 50 ms each. For example, "Natalie Rushman"
  gives Natasha Romanoff, and "Vormir" gives passages of Infinity War and Endgame.
- Rebuilding the graph recreates every index.

### Build (done 2026-11-26)

`src/retrieval/indexes.py`, run after `load_neo4j`, `profiles` and `load_summaries`. `load_neo4j`
creates `entity_names`. The OpenRouter client (embeddings only), the passage split and
`JsonHttpClient.post_json` come back from 4945497.

- **What is embedded (agreed 2026-11-26):** a passage's heading and text; a plot fact's whole
  fact line as the summary inputs show it (`[Q… ep N] Title: Subject RELATION Object: "evidence"
  (note: …)`), since many evidence sentences are fragments that don't say who acts or in which
  title; a summary's name and text.
- **Caches:** one file per kind in `processed_data/retrieval/embeddings/` (passages, evidence,
  summaries), each vector keyed by a hash of the text it embeds, with the model's name. The 738
  passage vectors of the first attempt were re-keyed into `passages.json`, so none were embedded
  again; the old `embeddings.json` is gone.
- **Indexes:** `passage_text`, `evidence_text` (evidence and note) and `summary_text` (name and
  text), full-text; `passage_embedding`, `evidence_embedding` and `summary_embedding`, vector.
  The evidence indexes cover all 14 plot relationship types in one index each (Neo4j 2026.10
  accepts several types). Search indexes are dropped and created on every run, so they always
  match the code; lookup indexes are created if missing. `actor_key` was a stale constraint and
  was dropped once.
- **Result:** 738 passage, 3,552 fact and 534 summary vectors (3,549 distinct fact lines and 534
  summaries embedded, well under a cent); a second run embedded nothing.
- **Validation** (`tests/neo4j/test_indexes.py`): exactly the expected indexes, all ONLINE; every
  passage, fact and summary has a 1,536-dimension vector; each vector index finds a stored
  vector's own item first; keyword lookups under 50 ms (median of three after a warm-up).
  Two expectations above were wrong and were corrected: "Natalie Rushman" first finds the Thing
  of that name (Natasha IMPERSONATES it in Iron Man 2), then Natasha; and no Endgame fact names
  the Soul Stone, so "Soul Stone" finds Infinity War facts only. A probe by meaning, "who
  sacrificed themselves", gave five sacrifices among the top five facts (Stark, Bakshi,
  Nightcrawler, Riri and F.R.I.D.A.Y.).

## Open points
- **Aggregation on retrieved data** (settled 2026-11-27). A count is right only if it rests on
  the whole set, so the aggregation tool queries the whole graph instead of counting retrieved
  data (see "Global search, DRIFT and the aggregation tool").
- **The leftover passages and indexes** are reused and are now part of the build (see "Index
  set", "Build").
