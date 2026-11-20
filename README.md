# MCU_GraphRAG

A knowledge graph of the Marvel screen universe (MCU plus the Fox X-Men films)
and a GraphRAG chatbot built on it. The graph answers multi-hop, timeline,
identity/variant and affiliation questions that plain retrieval struggles with.

Scope and data sources are defined in [docs/data_sources_and_tiers.md](docs/data_sources_and_tiers.md).

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install requests python-dotenv mwparserfromhell neo4j pytest
```

Copy `.env.example` to `.env` and fill in a TMDB API key and a Neo4j password of your choice.

The graph database (Neo4j Community, version pinned in `docker-compose.yml`) runs in Docker:

```powershell
docker compose up -d --wait   # start Neo4j; the graph is kept in the mcu-neo4j-data volume
docker compose down           # stop it (add -v to delete the graph)
```

Neo4j Browser is at http://localhost:7474 (user `neo4j`, the password from `.env`).

## Collecting data

Collected data is written to `source_data/`, which is not committed (see [Data licensing](#data-licensing)).

Collection is incremental: a rerun fetches only titles that are new or whose scope changed
(for example a series gaining a season), and only new credits, people and wiki pages; what
was collected before is kept with its original `retrieved_at`. Each title-based collector
records what it collected in `source_data/collection_scopes/`.

```powershell
.venv\Scripts\python.exe -m src.source_data_collection.build_title_registry   # titles, QIDs, crosswalk IDs
.venv\Scripts\python.exe -m src.source_data_collection.collect_cast           # cast from TMDB, Wikidata, Wikipedia
.venv\Scripts\python.exe -m src.source_data_collection.collect_plots          # plot and episode summaries
.venv\Scripts\python.exe -m src.source_data_collection.collect_characters     # character names, universes, variants
.venv\Scripts\python.exe -m src.source_data_collection.collect_mcu_wiki       # MCU wiki pages: supporting characters, aliases, species
.venv\Scripts\python.exe -m src.source_data_collection.collect_title_details  # directors, writers, first release, sequels
.venv\Scripts\python.exe -m src.source_data_collection.collect_title_stats    # box office, budget, runtime, ratings
.venv\Scripts\python.exe -m src.source_data_collection.collect_phases         # MCU phases (Wikipedia and Wikidata)
.venv\Scripts\python.exe -m src.source_data_collection.collect_teams          # team members (MCU wiki and Marvel Database), team articles
.venv\Scripts\python.exe -m src.source_data_collection.collect_timeline       # in-universe timeline (MCU wiki and Wikipedia)
.venv\Scripts\python.exe -m src.source_data_collection.collect_production     # Wikipedia production / development sections
```

Merged tables built from the collected data are written to `processed_data/` (not committed):

```powershell
.venv\Scripts\python.exe -m src.processing.build_titles                       # first release, release order, phases, sagas, timeline
.venv\Scripts\python.exe -m src.processing.build_characters                   # one character per reality, aliases, variant links
.venv\Scripts\python.exe -m src.processing.build_teams                        # teams and memberships linked to characters
```

## Extracting facts from plots

Facts (who fights, helps, kills or joins whom, with an exact quote as evidence) are extracted
from the plot and episode summaries by Claude Code subagents (Sonnet), following
[src/graph/extraction_prompt.md](src/graph/extraction_prompt.md). Output goes to
`processed_data/extraction/plots/` (not committed).

```powershell
.venv\Scripts\python.exe -m src.graph.prepare_extraction   # chunk inputs; lists pending chunks per agent in batches.json
.venv\Scripts\python.exe -m src.graph.check_extraction     # check every output: known IDs, exact evidence, episodes
```

Each agent gets one batch from `batches.json` (prompt and commands: [docs/extraction_agents.md](docs/extraction_agents.md)): for every chunk it reads `inputs/<chunk>.json`,
writes `outputs/<chunk>.json` and runs the check on it. A chunk is pending only when its output
is missing or older than its input, so a rerun extracts only new or changed text.

## Loading the graph

With Neo4j running (`docker compose up -d --wait`), load the built tables and the extracted facts.
Each run rebuilds the graph from the tables (about 15 seconds). What every node and
relationship means, and where it comes from: [docs/db_schematics.md](docs/db_schematics.md).

```powershell
.venv\Scripts\python.exe -m src.graph.load_neo4j   # Title, Character, Actor, Team, Thing nodes; plot facts as edges
.venv\Scripts\python.exe -m pytest -m neo4j        # check the loaded graph
.venv\Scripts\python.exe -m src.graph.evaluate     # run the 50 evaluation questions (docs/evaluation_questions.md)
```

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -m "not validation and not neo4j"   # unit tests (offline)
.venv\Scripts\python.exe -m pytest -m validation                       # checks on collected data (run after collecting)
.venv\Scripts\python.exe -m pytest -m neo4j                            # checks on the running database
```

## Credits

### Data sources

This project is built on openly licensed and publicly documented data. Thanks to
the volunteers and teams who maintain these sources.

| Source | Used for | License / terms | Status |
| --- | --- | --- | --- |
| [Wikidata](https://www.wikidata.org/) | Titles, IDs, cast, characters, dates | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | In use |
| [Wikipedia](https://en.wikipedia.org/) | Plot summaries, cast sections | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); text from Wikipedia contributors | In use |
| [TMDB](https://www.themoviedb.org/) | Cast and character credits, billing order, ID crosswalk | [TMDB API Terms of Use](https://www.themoviedb.org/api-terms-of-use) | In use |
| [Marvel Database](https://marvel.fandom.com/) (Fandom) | Character names, aliases, reality (Earth designation), affiliations | [CC BY-SA 3.0](https://www.fandom.com/licensing); text from Marvel Database contributors | In use |
| [Marvel Cinematic Universe Wiki](https://marvelcinematicuniverse.fandom.com/) (Fandom) | Supporting characters missing from Wikidata (matched by actor), aliases, species, in-universe timeline, teams | [CC BY-SA 3.0](https://www.fandom.com/licensing); text from MCU Wiki contributors | In use |
| [Comic Vine](https://comicvine.gamespot.com/api/) | Comic storylines and issues (metadata only) | Comic Vine API terms | Planned |
| [Grand Comics Database](https://www.comics.org/) | Issue-level character appearances | GCD data license (to be checked before use) | Planned |
| Box Office Mojo / The Numbers | Spot checks of box office figures only; no data redistributed | Site terms | Planned |

**TMDB notice:** This product uses the TMDB API but is not endorsed or certified by
[TMDB](https://www.themoviedb.org/). The TMDB logo will also be shown in the chatbot UI.

Marvel characters, titles and related names are trademarks of Marvel / Disney.
This is an independent, non-commercial study project and is not affiliated with
or endorsed by Marvel, Disney, Fox or Sony.

## Data licensing

The code in this repository is MIT licensed (see [LICENSE](LICENSE)). Collected
data keeps the license of its source: Wikipedia text stays CC BY-SA 4.0 and
requires attribution if shared; TMDB data is subject to the TMDB API terms. Every
collected record stores `source`, `source_url`, `retrieved_at` and `license`.
