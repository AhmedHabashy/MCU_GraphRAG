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

"Reality" is the main reality the title is set in, as an Earth designation. The main MCU
universe is **Earth-616**, as the films call it (confirmed by the MCU expert). The Marvel
Database names that page "Earth-199999" and uses "Earth-616" for the comics. Comics are
out of scope for now, so in this project Earth-616 always means the MCU.
The column is curated, because Wikidata files the whole MCU under one universe
and Marvel Database pages are per character, not per film. A character whose own screen
version is in another reality (e.g. the Raimi Green Goblin in No Way Home) keeps that
reality, but only if it is a reality named in this tier list or in "Curated roles" below
(sources also list video-game realities). The title's reality is the default for everyone
else. Roles the data gets wrong are fixed in "Curated roles".

All realities below are confirmed by the MCU expert:

- The Deadpool films are set in Earth-10005 (named in Deadpool & Wolverine; the X-Men
  cameo in Deadpool 2).
- The Fox films after X-Men: Days of Future Past stay in Earth-10005: time travel changed
  the events, not the reality. The New Mutants is a standalone film, but belongs to the X-Men
  universe, so it is Earth-10005 too.
- What If...? has no single reality; it is a set of stories in different, unnumbered
  realities, so "Multiverse". Only seasons 1-2 are in scope.

| Title | Type | Year | Universe | Reality |
| --- | --- | --- | --- | --- |
| Iron Man | Film | 2008 | MCU | Earth-616 |
| Iron Man 2 | Film | 2010 | MCU | Earth-616 |
| Captain America: The First Avenger | Film | 2011 | MCU | Earth-616 |
| Thor | Film | 2011 | MCU | Earth-616 |
| The Avengers | Film | 2012 | MCU | Earth-616 |
| Iron Man 3 | Film | 2013 | MCU | Earth-616 |
| Thor: The Dark World | Film | 2013 | MCU | Earth-616 |
| Captain America: The Winter Soldier | Film | 2014 | MCU | Earth-616 |
| Avengers: Age of Ultron | Film | 2015 | MCU | Earth-616 |
| Captain America: Civil War | Film | 2016 | MCU | Earth-616 |
| Doctor Strange | Film | 2016 | MCU | Earth-616 |
| Spider-Man: Homecoming | Film | 2017 | MCU | Earth-616 |
| Thor: Ragnarok | Film | 2017 | MCU | Earth-616 |
| Black Panther | Film | 2018 | MCU | Earth-616 |
| Avengers: Infinity War | Film | 2018 | MCU | Earth-616 |
| Avengers: Endgame | Film | 2019 | MCU | Earth-616 |
| Spider-Man: Far From Home | Film | 2019 | MCU | Earth-616 |
| Black Widow | Film | 2021 | MCU | Earth-616 |
| Shang-Chi and the Legend of the Ten Rings | Film | 2021 | MCU | Earth-616 |
| Spider-Man: No Way Home | Film | 2021 | MCU | Earth-616 |
| Loki, season 1 | Series | 2021 | MCU | Earth-616 |
| The Falcon and the Winter Soldier | Series | 2021 | MCU | Earth-616 |
| What If...? (added), seasons 1-2 | Animated series | 2021-2023 | MCU | Multiverse |
| Doctor Strange in the Multiverse of Madness | Film | 2022 | MCU | Earth-616 |
| Thor: Love and Thunder (added) | Film | 2022 | MCU | Earth-616 |
| Black Panther: Wakanda Forever | Film | 2022 | MCU | Earth-616 |
| Ant-Man and the Wasp: Quantumania | Film | 2023 | MCU | Earth-616 |
| Loki, season 2 | Series | 2023 | MCU | Earth-616 |
| The Marvels | Film | 2023 | MCU | Earth-616 |
| Deadpool & Wolverine | Film | 2024 | MCU | Earth-10005 |
| Captain America: Brave New World | Film | 2025 | MCU | Earth-616 |
| Thunderbolts\* | Film | 2025 | MCU | Earth-616 |
| The Fantastic Four: First Steps | Film | 2025 | MCU | Earth-828 |
| Spider-Man: Brand New Day (added) | Film | 2026 | MCU | Earth-616 |
| Avengers: Doomsday (added) | Film | 2026 (Dec 18, upcoming) | MCU | Earth-616 |
| X-Men | Film | 2000 | Fox X-Men | Earth-10005 |
| X2 | Film | 2003 | Fox X-Men | Earth-10005 |
| X-Men: The Last Stand | Film | 2006 | Fox X-Men | Earth-10005 |
| X-Men Origins: Wolverine | Film | 2009 | Fox X-Men | Earth-10005 |
| X-Men: First Class | Film | 2011 | Fox X-Men | Earth-10005 |
| The Wolverine | Film | 2013 | Fox X-Men | Earth-10005 |
| X-Men: Days of Future Past | Film | 2014 | Fox X-Men | Earth-10005 |
| Deadpool | Film | 2016 | Fox X-Men | Earth-10005 |
| X-Men: Apocalypse | Film | 2016 | Fox X-Men | Earth-10005 |
| Logan | Film | 2017 | Fox X-Men | Earth-17315 |
| Deadpool 2 | Film | 2018 | Fox X-Men | Earth-10005 |
| Dark Phoenix | Film | 2019 | Fox X-Men | Earth-10005 |
| The New Mutants | Film | 2020 | Fox X-Men | Earth-10005 |
| X-Men '97 (added) | Animated series | 2024-2026 | MCU animation | Earth-92131 |

### Curated roles

Corrections from the MCU expert for single roles the data gets wrong: crossover characters
who keep their home reality, variants that must stay separate, and wrong character links.
A blank cell keeps what the data says. "Title" is a Tier 1 title, or `*` for every title.
"Identity" is a Wikidata QID or `mcuwiki:<Page>`. "Reality" is an Earth designation, or
`Unknown` when the expert confirmed the role comes from another universe that has no known
number. "Variant of" links the role as a variant of that Wikidata character. Rows marked †
are the expert's best guess or still open.

| Title | Actor | Character | Identity | Reality | Variant of |
| --- | --- | --- | --- | --- | --- |
| Spider-Man: No Way Home | Alfred Molina | Doctor Octopus | | Earth-96283 | |
| Spider-Man: No Way Home | Jamie Foxx | Electro | | Earth-120703 | |
| Spider-Man: No Way Home | Rhys Ifans | The Lizard | | Earth-120703 | |
| Avengers: Doomsday | Pedro Pascal | Reed Richards | | Earth-828 | |
| Avengers: Doomsday | Vanessa Kirby | Sue Storm | | Earth-828 | |
| Avengers: Doomsday | Joseph Quinn | Johnny Storm | | Earth-828 | |
| Avengers: Doomsday | Ebon Moss-Bachrach | Ben Grimm | | Earth-828 | |
| Avengers: Doomsday | Patrick Stewart | Charles Xavier | | Earth-10005 | |
| Avengers: Doomsday | Ian McKellen | Magneto | | Earth-10005 | |
| Avengers: Doomsday | James Marsden | Cyclops | | Earth-10005 | |
| Avengers: Doomsday | Kelsey Grammer | Beast | | Earth-10005 | |
| Avengers: Doomsday | Alan Cumming | Nightcrawler | | Earth-10005 | |
| Avengers: Doomsday | Rebecca Romijn | Mystique | | Earth-10005 | |
| Avengers: Doomsday | Channing Tatum | Gambit | | Earth-10005 † | |
| Deadpool & Wolverine | Hugh Jackman | Wolverine | mcuwiki:Wolverine | Unknown † | Q97275436 |
| Deadpool & Wolverine | Henry Cavill | Cavillrine | mcuwiki:Cavillrine | Unknown † | Q97275436 |
| Deadpool & Wolverine | Dafne Keen | X-23 | | Earth-17315 † | |
| Deadpool & Wolverine | Jennifer Garner | Elektra | | Unknown † | |
| Deadpool & Wolverine | Wesley Snipes | Blade | | Unknown † | |
| Deadpool & Wolverine | Channing Tatum | Gambit | | Unknown † | |
| Deadpool & Wolverine | Chris Evans | Johnny Storm | | Unknown † | |
| Doctor Strange in the Multiverse of Madness | Patrick Stewart | Professor X | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Hayley Atwell | Captain Carter | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Lashana Lynch | Captain Marvel | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Anson Mount | Black Bolt | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | John Krasinski | Reed Richards | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Chiwetel Ejiofor | Baron Mordo | | Earth-838 † | |
| The Marvels | Kelsey Grammer | Beast | | Earth-10005 | |
| * | Kerry Condon | F.R.I.D.A.Y. | Q28173125 | | |

### Phases and sagas

Marvel Studios' official structure of the MCU, in order. Which phase each title belongs to
comes from two sources that must agree: the Wikipedia "Marvel Cinematic Universe: Phase N"
articles and Wikidata. The Fox films and X-Men '97 are in no phase.

| Phase | Saga |
| --- | --- |
| Phase One | The Infinity Saga |
| Phase Two | The Infinity Saga |
| Phase Three | The Infinity Saga |
| Phase Four | The Multiverse Saga |
| Phase Five | The Multiverse Saga |
| Phase Six | The Multiverse Saga |

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
| Daredevil, seasons 1-3 | Series | 2015-2018 | Netflix |
| The Punisher, seasons 1-2 | Series | 2017-2019 | Netflix |

Netflix's Daredevil and The Punisher were promoted from Tier 3 (MCU expert), because
their characters reappear in the MCU.

### Tier 3: optional

Add these only if the questions need them.

| Title | Type | Year | Universe |
| --- | --- | --- | --- |
| Agents of S.H.I.E.L.D. (added), seasons 1-7 | Series | 2013-2020 | Marvel TV |
| Agent Carter (added), seasons 1-2 | Series | 2015-2016 | Marvel TV |
| Jessica Jones, seasons 1-2 | Series | 2015-2018 | Netflix |
| Luke Cage, seasons 1-2 | Series | 2016-2018 | Netflix |
| Iron Fist, seasons 1-2 | Series | 2017-2018 | Netflix |
| The Defenders | Series | 2017 | Netflix |
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
