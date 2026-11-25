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

| Grouping | Count | Written from |
| --- | --- | --- |
| Teams | 12 | members and roles (MEMBER_OF), plus the team's plot facts |
| Phases | 6 | the plot summaries of their titles |
| Sagas | 2 | the summaries of their phases |
| Universes | 10 | the plot summaries of their titles |
| Realities that span several universes | Earth-616 and Multiverse, for example | their characters and titles (the other realities repeat their universe) |
| Series (seasons or sequels joined by FOLLOWS) | 16 | the plot summaries of their titles |
| Main characters: at least 5 plot facts or 3 titles | 391 | names, reality, species, actors by title, appearances in release order, teams, variants, and the plot facts with their evidence sentences, grouped by title |

Every character, all 2,511, also gets a **profile** built from the graph without an LLM.
This makes every character searchable, and a profile can't hold anything the graph doesn't.
Of the 2,511, 1,571 have no plot fact.

Profiles (built 2026-11-25 by `src/graph/profiles.py`):

- One line per field: name and reality, aliases, species, actors (with how many titles),
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
- **The leftover passages and indexes** are reused (see "Index set"). Until they join the
  graph build, `tests/neo4j/test_graph.py::test_only_known_relation_types` fails on FROM.
