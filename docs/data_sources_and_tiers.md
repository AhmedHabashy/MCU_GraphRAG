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

The graph is built in three tiers: Tier 1 first, then Tier 2, then Tier 3. All three are collected.

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
A blank cell keeps what the data says. "Title" is a tier-list title, or `*` for every title.
"Actor" is an actor, or `*` for every role in a title set entirely in its own universe, whose
MCU-linked characters are local variants rather than visitors; a row for one actor wins.
"Identity" is a Wikidata QID or `mcuwiki:<Page>`. "Reality" is an Earth designation, or
`Unknown` when the expert confirmed the role comes from another universe that has no known
number. "Variant of" links the role as a variant of that Wikidata character. Rows marked †
are the expert's best guess (X-23 is probably from Logan's universe, though it was never
officially numbered). Channing Tatum's Gambit is one character in Deadpool & Wolverine and
Avengers: Doomsday (he escapes the Void in a deleted credits scene), from an unnumbered
universe. The No Way Home Spider-Men and villains need no rows: the data already gives each
one his own universe (Raimi Earth-96283, Webb Earth-120703), which the expert confirmed.
Round 3: the Watcher in I Am Groot is the What If...? Watcher; Morbius's Vulture is the MCU
Vulture of Spider-Man: Homecoming (a crossover that was later dropped); and He Who Remains
and Victor Timely are variants of Kang the Conqueror, like all of Quantumania's Kangs.

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
| Avengers: Doomsday | Channing Tatum | Gambit | | Unknown | |
| Deadpool & Wolverine | Hugh Jackman | Wolverine | mcuwiki:Wolverine | Unknown | Q97275436 |
| Deadpool & Wolverine | Henry Cavill | Cavillrine | mcuwiki:Cavillrine | Unknown | Q97275436 |
| Deadpool & Wolverine | Dafne Keen | X-23 | | Earth-17315 † | |
| Deadpool & Wolverine | Jennifer Garner | Elektra | | Earth-701306 | |
| Deadpool & Wolverine | Wesley Snipes | Blade | | Earth-26320 | |
| Deadpool & Wolverine | Channing Tatum | Gambit | | Unknown | |
| Deadpool & Wolverine | Chris Evans | Johnny Storm | | Earth-121698 | |
| Doctor Strange in the Multiverse of Madness | Patrick Stewart | Professor X | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Hayley Atwell | Captain Carter | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Lashana Lynch | Captain Marvel | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Anson Mount | Black Bolt | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | John Krasinski | Reed Richards | | Earth-838 | |
| Doctor Strange in the Multiverse of Madness | Chiwetel Ejiofor | Baron Mordo | | Earth-838 | |
| The Marvels | Kelsey Grammer | Beast | | Earth-10005 | |
| * | Kerry Condon | F.R.I.D.A.Y. | Q28173125 | | |
| Marvel Zombies | * | | | Earth-89521 | |
| Your Friendly Neighborhood Spider-Man | * | | | Earth-86445 | |
| I Am Groot | Jeffrey Wright | The Watcher | | Multiverse | |
| Morbius | Michael Keaton | Vulture | | Earth-616 | |
| Loki, season 1 | Jonathan Majors | He Who Remains | mcuwiki:He_Who_Remains | | Q1982051 |
| Loki, season 2 | Jonathan Majors | Victor Timely | mcuwiki:Victor_Timely | | Q1982051 |

### Dropped roles

Roles that Wikidata lists but that are not in the title (MCU expert, round 3). TMDB does not
credit them either. Each row drops every role of that actor in that title.

| Title | Actor | Reason |
| --- | --- | --- |
| The Guardians of the Galaxy Holiday Special | Zoe Saldaña | Wikidata has her as Drax; she is not in the special. |
| Black Panther: Wakanda Forever | Daniel Kaluuya | W'Kabi does not appear. |
| The Marvels | Randall Park | Jimmy Woo does not appear (last seen in WandaVision). |

### Verified first releases

Release dates checked by hand where the sources disagree by more than the premiere-to-release
window. A title's first release is its earliest release of any kind, premieres included;
these dates replace what the sources say.

| Title | First release | Event | Source |
| --- | --- | --- | --- |
| Jessica Jones | 2015-11-17 | New York premiere of the first two episodes; Netflix release 2015-11-20. Wikidata's 2015-10-20 has no source and is wrong. | Wikipedia, "Jessica Jones season 1" |
| Luke Cage | 2016-09-28 | Harlem premiere of the first two episodes; Netflix release 2016-09-30. Wikidata dates the first episode by this premiere. | Wikipedia, "Luke Cage season 1" |

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

### Teams

The teams that matter most for Avengers: Doomsday (MCU expert), one row per team and
reality. Members come from each team's MCU wiki and Marvel Database pages. Per the expert,
the New Avengers and the Thunderbolts are one team, and the Illuminati exist only in Doctor
Strange in the Multiverse of Madness. Team Doom is added once Avengers: Doomsday is released.
The Guardians of the Galaxy were confirmed by the expert (round 2): the team splits up at
the end of Guardians of the Galaxy Vol. 3, possibly not for good. Round 2 added no other teams
(the Eternals are a species on both wikis, not a team, so they are not listed). The Wikipedia page is kept as text for later extraction of who joins or leaves when.
Round 3 adds the Defenders and, as organizations, S.H.I.E.L.D., HYDRA and the Hand ("Kind"
is `team` or `organization`). The Inhuman Royal Family and the Fox Fantastic Fours are not
added (expert). The Sinister Six is not listed: the expert (round 4) confirmed no such group
exists on screen; the five No Way Home villains fought together but are never called that, and
the expert left it to us, so no team is invented for them. Per round 4, Daisy Johnson is linked
to S.H.I.E.L.D. (a member, and a former director) and to the Inhumans through her species: each
character's species comes from its MCU wiki infobox (former, temporary and Framework species
are left out).
The Time Variance Authority (TVA) is added as an organization (user, after the extraction
pilot). It stands outside time; it is placed in Earth-616 with Loki, whose seasons are set
there. Its Marvel Database page covers the comics and the screen TVA together, so only the
MCU wiki page is used (comics are out of scope).

| Team | Reality | Kind | MCU wiki page | Marvel Database page | Wikipedia page | Also called |
| --- | --- | --- | --- | --- | --- | --- |
| Avengers | Earth-616 | team | Avengers | Avengers (Earth-199999) | Avengers (Marvel Cinematic Universe) | |
| New Avengers | Earth-616 | team | New Avengers | New Avengers (Earth-199999) | Avengers (Marvel Cinematic Universe) | Thunderbolts |
| Fantastic Four | Earth-828 | team | Fantastic Four | Fantastic Four (Earth-828) | List of Marvel Cinematic Universe teams and organizations | |
| X-Men | Earth-10005 | team | | X-Men (Earth-10005) | X-Men in film | |
| X-Men | Earth-92131 | team | | X-Men (Earth-92131) | | |
| Illuminati | Earth-838 | team | Illuminati | Illuminati (Earth-838) | List of Marvel Cinematic Universe teams and organizations | |
| Guardians of the Galaxy | Earth-616 | team | Guardians of the Galaxy | Guardians of the Galaxy (Earth-199999) | List of Marvel Cinematic Universe teams and organizations | |
| Defenders | Earth-616 | team | Defenders | Defenders (Earth-199999) | List of Marvel Cinematic Universe teams and organizations | |
| S.H.I.E.L.D. | Earth-616 | organization | S.H.I.E.L.D. | S.H.I.E.L.D. (Earth-199999) | List of Marvel Cinematic Universe teams and organizations | |
| HYDRA | Earth-616 | organization | Hydra | Hydra (Earth-199999) | List of Marvel Cinematic Universe teams and organizations | |
| The Hand | Earth-616 | organization | Hand | Hand (Earth-199999) | List of Marvel Cinematic Universe teams and organizations | |
| Time Variance Authority | Earth-616 | organization | Time Variance Authority | | List of Marvel Cinematic Universe teams and organizations | TVA |

### Tier 2: remaining MCU films and Disney+ series (second pass)

"Reality" works as in Tier 1; all realities are confirmed by the MCU expert (round 2). The
Netflix series and Eyes of Wakanda are the main MCU. Marvel Zombies is the sequel to the
zombie episode of What If...?, set on Earth-89521.
I Am Groot has no separate season items on Wikidata, so its two seasons are one title.

| Title | Type | Year | Universe | Reality |
| --- | --- | --- | --- | --- |
| The Incredible Hulk | Film | 2008 | MCU | Earth-616 |
| Guardians of the Galaxy | Film | 2014 | MCU | Earth-616 |
| Ant-Man | Film | 2015 | MCU | Earth-616 |
| Guardians of the Galaxy Vol. 2 | Film | 2017 | MCU | Earth-616 |
| Ant-Man and the Wasp | Film | 2018 | MCU | Earth-616 |
| Captain Marvel | Film | 2019 | MCU | Earth-616 |
| WandaVision | Series | 2021 | MCU | Earth-616 |
| Hawkeye | Series | 2021 | MCU | Earth-616 |
| Eternals | Film | 2021 | MCU | Earth-616 |
| Moon Knight | Series | 2022 | MCU | Earth-616 |
| Ms. Marvel | Series | 2022 | MCU | Earth-616 |
| She-Hulk: Attorney at Law | Series | 2022 | MCU | Earth-616 |
| Werewolf by Night | Special | 2022 | MCU | Earth-616 |
| The Guardians of the Galaxy Holiday Special | Special | 2022 | MCU | Earth-616 |
| I Am Groot, seasons 1-2 | Animated shorts | 2022-2023 | MCU | Earth-616 |
| Guardians of the Galaxy Vol. 3 | Film | 2023 | MCU | Earth-616 |
| Secret Invasion | Series | 2023 | MCU | Earth-616 |
| Echo | Series | 2024 | MCU | Earth-616 |
| Agatha All Along | Series | 2024 | MCU | Earth-616 |
| Daredevil: Born Again | Series | 2025 | MCU | Earth-616 |
| Ironheart | Series | 2025 | MCU | Earth-616 |
| Your Friendly Neighborhood Spider-Man | Animated series | 2025 | MCU animation | Earth-86445 |
| Eyes of Wakanda | Animated series | 2025 | MCU animation | Earth-616 |
| Marvel Zombies | Animated series | 2025 | MCU animation | Earth-89521 |
| Wonder Man | Series | 2026 | MCU | Earth-616 |
| VisionQuest | Series | 2026 | MCU | Earth-616 |
| Daredevil, seasons 1-3 | Series | 2015-2018 | Netflix | Earth-616 |
| The Punisher, seasons 1-2 | Series | 2017-2019 | Netflix | Earth-616 |

Netflix's Daredevil and The Punisher were promoted from Tier 3 (MCU expert), because
their characters reappear in the MCU.

### Tier 3: other Marvel TV series and non-MCU Marvel films

Collected for completeness. "Reality" works as in Tier 1; every reality here is confirmed
by the MCU expert (round 3). Per the expert, the Raimi and Webb films matter for Spider-Man:
No Way Home, and Jessica Jones, Luke Cage, Iron Fist and The Defenders for Daredevil: Born
Again; the other Tier 3 titles do not connect to anything else. Agents of S.H.I.E.L.D. is
the main MCU, although from season 5 on it ignores the films' events (such as the snap).

| Title | Type | Year | Universe | Reality |
| --- | --- | --- | --- | --- |
| Agents of S.H.I.E.L.D. (added), seasons 1-7 | Series | 2013-2020 | Marvel TV | Earth-616 |
| Agent Carter (added), seasons 1-2 | Series | 2015-2016 | Marvel TV | Earth-616 |
| Jessica Jones, seasons 1-3 | Series | 2015-2019 | Netflix | Earth-616 |
| Luke Cage, seasons 1-2 | Series | 2016-2018 | Netflix | Earth-616 |
| Iron Fist, seasons 1-2 | Series | 2017-2018 | Netflix | Earth-616 |
| The Defenders | Series | 2017 | Netflix | Earth-616 |
| Inhumans | Series | 2017 | ABC | Earth-616 |
| Fantastic Four (added) | Film | 2005 | Fox Fantastic Four | Earth-121698 |
| Fantastic Four: Rise of the Silver Surfer (added) | Film | 2007 | Fox Fantastic Four | Earth-121698 |
| Fantastic Four (added) | Film | 2015 | Fox Fantastic Four | Earth-15866 |
| Spider-Man | Film | 2002 | Raimi Spider-Man | Earth-96283 |
| Spider-Man 2 | Film | 2004 | Raimi Spider-Man | Earth-96283 |
| Spider-Man 3 | Film | 2007 | Raimi Spider-Man | Earth-96283 |
| The Amazing Spider-Man | Film | 2012 | Webb Spider-Man | Earth-120703 |
| The Amazing Spider-Man 2 | Film | 2014 | Webb Spider-Man | Earth-120703 |
| Venom | Film | 2018 | Sony Spider-Man Universe | Earth-688B |
| Venom: Let There Be Carnage | Film | 2021 | Sony Spider-Man Universe | Earth-688B |
| Morbius | Film | 2022 | Sony Spider-Man Universe | Earth-688B |
| Madame Web | Film | 2024 | Sony Spider-Man Universe | Earth-688B |
| Kraven the Hunter | Film | 2024 | Sony Spider-Man Universe | Earth-688B |
| Venom: The Last Dance | Film | 2024 | Sony Spider-Man Universe | Earth-688B |
