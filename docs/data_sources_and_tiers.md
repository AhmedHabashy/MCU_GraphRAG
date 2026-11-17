# Data Sources and Title Tiers

This file is the tracked, reproducible definition of the project's data scope.
The collection code (`src/source_data_collection/tier_titles.py`) reads the tier
tables below directly, so keep the table format unchanged: four columns
`Title | Type | Year | Universe`, one title per row.

## Data sources

Full film transcripts are copyrighted, so they are not used. Wikipedia plot
summaries (CC BY-SA) cover the same story information and can be shared with
attribution, so they are the main text source.

| Source | What it gives | Notes |
| --- | --- | --- |
| Wikidata | Films, characters, actors, directors, release dates | Already graph-shaped; CC0 |
| Wikipedia | Plot summaries, cast sections | Main text for relationship extraction; CC BY-SA |
| Marvel Fandom wiki | Bios, powers, affiliations, variants | CC BY-SA; good for aliases |
| TMDB API | Cast and crew, character-to-actor mappings | Check attribution terms |
| Comic Vine / Marvel API | Comics metadata for Doom and the Fantastic Four | Metadata only, not comic text |
| Fox X-Men and Fantastic Four films | Cast overlap with Doomsday | Include in scope |
| Timeline and box office data | Release order, in-universe years, earnings | Enables timeline and analytics questions |

Every collected record stores `source`, `source_url`, `retrieved_at`, `license`
and the ID crosswalk (`wikidata_qid`, `tmdb_id`, `imdb_id`).

## Title tiers

The graph is built in three tiers: Tier 1 first, then Tier 2, then Tier 3 only if needed.

Notes on the list:

- Rows are not grouped by phase. `release_order` and `in_universe_year` are
  separate fields, filled from Wikidata and the timeline pages.
- "Year" is the first release year; for multi-year titles the collector uses the first year.
- Only Venom, Morbius, Madame Web and Kraven are the Sony Spider-Man Universe.
  The Raimi and Webb Spider-Man films are separate continuities.
- Titles marked "(added)" were missing from the original fan-supplied list.
- A title of the form `Name, season N` is collected as a TV season.

### Tier 1: core for Doomsday (load first)

"Reality" is the main reality the title is set in, as a Marvel Database Earth
designation. It is curated, because Wikidata files the whole MCU under one universe
and Marvel Database pages are per character, not per film. A character with its own
screen version in another reality (e.g. the Raimi Green Goblin in No Way Home) keeps
that reality; the title's reality is the default for everyone else.
Rows marked † need review by the MCU expert:

- Deadpool, Deadpool 2: Deadpool & Wolverine names Deadpool's home Earth-10005, while
  some Marvel Database pages place the Deadpool films in Earth-TRN414.
- X-Men: Days of Future Past, X-Men: Apocalypse, Dark Phoenix, The New Mutants: the
  revised Fox timeline after Days of Future Past. Wikidata calls it Earth-TRN414, but the
  Marvel Database no longer has that page and files the Fox films under Earth-10005, so
  Earth-10005 is used.
- What If...?: an anthology across many realities, so "Multiverse".

| Title | Type | Year | Universe | Reality |
| --- | --- | --- | --- | --- |
| Iron Man | Film | 2008 | MCU | Earth-199999 |
| Iron Man 2 | Film | 2010 | MCU | Earth-199999 |
| Captain America: The First Avenger | Film | 2011 | MCU | Earth-199999 |
| Thor | Film | 2011 | MCU | Earth-199999 |
| The Avengers | Film | 2012 | MCU | Earth-199999 |
| Iron Man 3 | Film | 2013 | MCU | Earth-199999 |
| Thor: The Dark World | Film | 2013 | MCU | Earth-199999 |
| Captain America: The Winter Soldier | Film | 2014 | MCU | Earth-199999 |
| Avengers: Age of Ultron | Film | 2015 | MCU | Earth-199999 |
| Captain America: Civil War | Film | 2016 | MCU | Earth-199999 |
| Doctor Strange | Film | 2016 | MCU | Earth-199999 |
| Spider-Man: Homecoming | Film | 2017 | MCU | Earth-199999 |
| Thor: Ragnarok | Film | 2017 | MCU | Earth-199999 |
| Black Panther | Film | 2018 | MCU | Earth-199999 |
| Avengers: Infinity War | Film | 2018 | MCU | Earth-199999 |
| Avengers: Endgame | Film | 2019 | MCU | Earth-199999 |
| Spider-Man: Far From Home | Film | 2019 | MCU | Earth-199999 |
| Black Widow | Film | 2021 | MCU | Earth-199999 |
| Shang-Chi and the Legend of the Ten Rings | Film | 2021 | MCU | Earth-199999 |
| Spider-Man: No Way Home | Film | 2021 | MCU | Earth-199999 |
| Loki, season 1 | Series | 2021 | MCU | Earth-199999 |
| The Falcon and the Winter Soldier | Series | 2021 | MCU | Earth-199999 |
| What If...? (added) | Animated series | 2021-2024 | MCU | Multiverse † |
| Doctor Strange in the Multiverse of Madness | Film | 2022 | MCU | Earth-199999 |
| Thor: Love and Thunder (added) | Film | 2022 | MCU | Earth-199999 |
| Black Panther: Wakanda Forever | Film | 2022 | MCU | Earth-199999 |
| Ant-Man and the Wasp: Quantumania | Film | 2023 | MCU | Earth-199999 |
| Loki, season 2 | Series | 2023 | MCU | Earth-199999 |
| The Marvels | Film | 2023 | MCU | Earth-199999 |
| Deadpool & Wolverine | Film | 2024 | MCU | Earth-10005 |
| Captain America: Brave New World | Film | 2025 | MCU | Earth-199999 |
| Thunderbolts\* | Film | 2025 | MCU | Earth-199999 |
| The Fantastic Four: First Steps | Film | 2025 | MCU | Earth-828 |
| Spider-Man: Brand New Day (added) | Film | 2026 | MCU | Earth-199999 |
| Avengers: Doomsday (added) | Film | 2026 (Dec 18, upcoming) | MCU | Earth-199999 |
| X-Men | Film | 2000 | Fox X-Men | Earth-10005 |
| X2 | Film | 2003 | Fox X-Men | Earth-10005 |
| X-Men: The Last Stand | Film | 2006 | Fox X-Men | Earth-10005 |
| X-Men Origins: Wolverine | Film | 2009 | Fox X-Men | Earth-10005 |
| X-Men: First Class | Film | 2011 | Fox X-Men | Earth-10005 |
| The Wolverine | Film | 2013 | Fox X-Men | Earth-10005 |
| X-Men: Days of Future Past | Film | 2014 | Fox X-Men | Earth-10005 † |
| Deadpool | Film | 2016 | Fox X-Men | Earth-10005 † |
| X-Men: Apocalypse | Film | 2016 | Fox X-Men | Earth-10005 † |
| Logan | Film | 2017 | Fox X-Men | Earth-17315 |
| Deadpool 2 | Film | 2018 | Fox X-Men | Earth-10005 † |
| Dark Phoenix | Film | 2019 | Fox X-Men | Earth-10005 † |
| The New Mutants | Film | 2020 | Fox X-Men | Earth-10005 † |
| X-Men '97 (added) | Animated series | 2024-2026 | MCU animation | Earth-92131 |

### Tier 2: remaining MCU films and Disney+ series (second pass)

| Title | Type | Year | Universe |
| --- | --- | --- | --- |
| The Incredible Hulk | Film | 2008 | MCU |
| Guardians of the Galaxy | Film | 2014 | MCU |
| Ant-Man | Film | 2015 | MCU |
| Guardians of the Galaxy Vol. 2 | Film | 2017 | MCU |
| Ant-Man and the Wasp | Film | 2018 | MCU |
| Captain Marvel | Film | 2019 | MCU |
| WandaVision | Series | 2021 | MCU |
| Hawkeye | Series | 2021 | MCU |
| Eternals | Film | 2021 | MCU |
| Moon Knight | Series | 2022 | MCU |
| Ms. Marvel | Series | 2022 | MCU |
| She-Hulk: Attorney at Law | Series | 2022 | MCU |
| Werewolf by Night | Special | 2022 | MCU |
| The Guardians of the Galaxy Holiday Special | Special | 2022 | MCU |
| I Am Groot, season 1 | Animated shorts | 2022 | MCU |
| Guardians of the Galaxy Vol. 3 | Film | 2023 | MCU |
| Secret Invasion | Series | 2023 | MCU |
| I Am Groot, season 2 | Animated shorts | 2023 | MCU |
| Echo | Series | 2024 | MCU |
| Agatha All Along | Series | 2024 | MCU |
| Daredevil: Born Again | Series | 2025 | MCU |
| Ironheart | Series | 2025 | MCU |
| Your Friendly Neighborhood Spider-Man | Animated series | 2025 | MCU animation |
| Eyes of Wakanda | Animated series | 2025 | MCU animation |
| Marvel Zombies | Animated series | 2025 | MCU animation |
| Wonder Man | Series | 2026 | MCU |
| VisionQuest | Series | 2026 | MCU |

### Tier 3: optional

Add these only if the questions need them. Promote Netflix Daredevil and
The Punisher to Tier 2 to cover their later MCU appearances.

| Title | Type | Year | Universe |
| --- | --- | --- | --- |
| Agents of S.H.I.E.L.D. (added), seasons 1-7 | Series | 2013-2020 | Marvel TV |
| Agent Carter (added), seasons 1-2 | Series | 2015-2016 | Marvel TV |
| Daredevil, seasons 1-3 | Series | 2015-2018 | Netflix |
| Jessica Jones, seasons 1-2 | Series | 2015-2018 | Netflix |
| Luke Cage, seasons 1-2 | Series | 2016-2018 | Netflix |
| Iron Fist, seasons 1-2 | Series | 2017-2018 | Netflix |
| The Defenders | Series | 2017 | Netflix |
| The Punisher, seasons 1-2 | Series | 2017-2019 | Netflix |
| Inhumans | Series | 2017 | ABC |
| Fantastic Four (added) | Film | 2005 | Fox Fantastic Four |
| Fantastic Four: Rise of the Silver Surfer (added) | Film | 2007 | Fox Fantastic Four |
| Fantastic Four (added) | Film | 2015 | Fox Fantastic Four |
| Spider-Man | Film | 2002 | Raimi Spider-Man |
| Spider-Man 2 | Film | 2004 | Raimi Spider-Man |
| Spider-Man 3 | Film | 2007 | Raimi Spider-Man |
| The Amazing Spider-Man | Film | 2012 | Webb Spider-Man |
| The Amazing Spider-Man 2 | Film | 2014 | Webb Spider-Man |
| Venom | Film | 2018 | Sony Spider-Man Universe |
| Venom: Let There Be Carnage | Film | 2021 | Sony Spider-Man Universe |
| Morbius | Film | 2022 | Sony Spider-Man Universe |
| Madame Web | Film | 2024 | Sony Spider-Man Universe |
| Kraven the Hunter | Film | 2024 | Sony Spider-Man Universe |
| Venom: The Last Dance | Film | 2024 | Sony Spider-Man Universe |
