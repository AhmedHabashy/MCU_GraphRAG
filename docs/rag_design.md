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

### Storage and updates

- The source of truth is files in `processed_data/summaries/`, one per summary. Each holds the
  text, the key facts, the sources, the writer and a hash of the input. Reloading the graph
  clears the database, but these files survive, so nothing is written twice.
- In Neo4j, each summary becomes a `Summary` node linked to what it describes. Phases, sagas
  and universes have no node of their own, so their summary links to its member titles.
- A summary is rewritten only when the hash of its input changes (the project's
  only-redo-what-changed rule).

## How we judge retrieval

We judge retrieval on its own, before any answer is written. For each strategy and each
evaluation question (docs/evaluation_questions.md) we measure:

- **quality**: does the retrieved data contain the facts the expected answer rests on?
- **speed**: how long does retrieval take?

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

## Open points


- **Aggregation on retrieved data.** A count is right only if retrieval brought back the
  whole set being counted. "Who directed the most films?" needs every title. So the
  aggregation tool may need its retrieval to fetch complete sets.
- **The leftover passages and indexes** are reused (see "Index set"). The graph rebuild of
  2026-11-26 removed them from Neo4j. The vectors are still cached in
  `processed_data/retrieval/embeddings.json`, and the code is in git history (4945497).
