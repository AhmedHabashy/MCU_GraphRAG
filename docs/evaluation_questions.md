# Evaluation questions

Fifty questions the graph must answer, across the question types in the project plan.
They have two jobs: the schema is checked against them before it is built, and they
are the evaluation set once it is. Comics questions are left out, since comics are out of
scope for now.

"Source" says where the expected answer comes from:

- **data**: computed from the collected data (Tiers 1 to 3), so the graph must reproduce
  it exactly. Box office and budgets are Wikidata's in US dollars, or TMDB's where Wikidata
  has none (Captain America: Brave New World's box office); ratings are TMDB's, as of
  collection (2026-11-19).
- **plot text**: events that exist only in the plot and episode summaries, so they must be
  extracted. The MCU expert confirmed these answers (round 3).
- **expert**: an MCU expert decision (docs/data_sources_and_tiers.md).

| ID | Type | Question | Expected answer | Source |
| --- | --- | --- | --- | --- |
| Q01 | Multi-hop | Which Avengers: Doomsday cast members also played their characters in the Fox X-Men films? | Patrick Stewart (Charles Xavier), Ian McKellen (Magneto), James Marsden (Cyclops), Kelsey Grammer (Beast), Alan Cumming (Nightcrawler) and Rebecca Romijn (Mystique), as the same Earth-10005 characters. | data |
| Q02 | Multi-hop | Which actors play two different major characters? | Chris Evans (Steve Rogers; Johnny Storm in the Fox Fantastic Four films and Deadpool & Wolverine), Robert Downey Jr. (Tony Stark; Victor von Doom in Avengers: Doomsday), Josh Brolin (Thanos; Cable in Deadpool 2), Oscar Isaac (Apocalypse; Moon Knight), Paul Bettany (J.A.R.V.I.S.; Vision), Peter Dinklage (Eitri; Bolivar Trask), Michael B. Jordan (Erik Killmonger; Johnny Storm in Fantastic Four (2015)), Aaron Taylor-Johnson (Pietro Maximoff; Kraven the Hunter) and Laurence Fishburne (Bill Foster; the voice of the Silver Surfer). | data |
| Q03 | Multi-hop | Who plays Wanda Maximoff, and in which titles does she appear? | Elizabeth Olsen. Earth-616: Captain America: The Winter Soldier, Avengers: Age of Ultron, Captain America: Civil War, Avengers: Infinity War, Avengers: Endgame, WandaVision, Doctor Strange in the Multiverse of Madness and VisionQuest. Variants: What If...? (Multiverse) and Marvel Zombies (Earth-89521). | data |
| Q04 | Multi-hop | Which characters in Spider-Man: No Way Home come from other universes, and who plays them? | From the Raimi universe (Earth-96283): Peter Parker (Tobey Maguire), Norman Osborn (Willem Dafoe), Doctor Octopus (Alfred Molina), Flint Marko (Thomas Haden Church). From the Webb universe (Earth-120703): Peter Parker (Andrew Garfield), Electro (Jamie Foxx), the Lizard (Rhys Ifans). Each is the same character as in his own films. Venom (Tom Hardy, Earth-688B) appears in the mid-credits scene. | data |
| Q05 | Multi-hop | Which actors from Netflix's Daredevil appear in other titles, and where? | Charlie Cox (Matt Murdock): No Way Home, She-Hulk, Echo, The Defenders, Daredevil: Born Again and, as a variant, Your Friendly Neighborhood Spider-Man. Vincent D'Onofrio (Wilson Fisk): Hawkeye, Echo, Born Again. Jon Bernthal (Frank Castle): The Punisher, Born Again, Spider-Man: Brand New Day. Deborah Ann Woll (Karen Page): The Punisher, The Defenders, Born Again. Elden Henson (Foggy Nelson): Jessica Jones, Luke Cage, The Defenders, Born Again. Rosario Dawson (Claire Temple): Jessica Jones, Luke Cage, Iron Fist, The Defenders. Élodie Yung (Elektra): The Defenders. Stephen Rider (Blake Tower): Luke Cage. Ayelet Zurer, Wilson Bethel and Toby Leonard Moore: Born Again. | data |
| Q06 | Multi-hop | Who plays Kang and his variants, and in which titles? | Jonathan Majors: He Who Remains in Loki season 1 and Victor Timely in Loki season 2, both variants of Kang the Conqueror, who appears in Ant-Man and the Wasp: Quantumania. | data |
| Q07 | Multi-hop | Which Avengers: Doomsday characters also appear in Avengers: Endgame? | Steve Rogers, Thor, Loki, Sam Wilson, Bucky Barnes, Scott Lang, Cassie Lang, Shuri, M'Baku and Peggy Carter. | data |
| Q08 | Multi-hop | Who directed the most films? | Anthony and Joe Russo, five each: Captain America: The Winter Soldier, Captain America: Civil War, Avengers: Infinity War, Avengers: Endgame and Avengers: Doomsday. Next are Bryan Singer (four X-Men films) and Sam Raimi (the three Spider-Man films and Doctor Strange in the Multiverse of Madness), with four each. | data |
| Q09 | Multi-hop | Which characters does Hugh Jackman play? | Logan in the Fox X-Men films (Earth-10005) and in Logan (Earth-17315), X-24 in Logan, and a different Wolverine variant in Deadpool & Wolverine (unnumbered universe). | data |
| Q10 | Multi-hop | Which actors play Tony Stark, and in which universes? | Robert Downey Jr. (Earth-616, ten titles from Iron Man to Avengers: Endgame) and Mick Wingert, who voices the What If...? variant (Multiverse) and the Your Friendly Neighborhood Spider-Man variant (Earth-86445). | data |
| Q11 | Timeline | Which title is set earliest in the in-universe timeline? | Eyes of Wakanda (from 1260 BC). The earliest film is Captain America: The First Avenger (1942 to 1945). | data |
| Q12 | Timeline | In what year is Captain Marvel set? | 1995. | data |
| Q13 | Timeline | Which MCU titles were released after Avengers: Endgame but are set before it? | Black Widow (2016), I Am Groot (2014) and Eyes of Wakanda (1260 BC to 1896). What If...? spans many times in other universes. | data |
| Q14 | Timeline | In what in-universe order do the Phase One films happen? | Captain America: The First Avenger, Iron Man, Iron Man 2, Thor, The Incredible Hulk, The Avengers. | data |
| Q15 | Timeline | How long after the snap is it reversed? | Five years: Avengers: Endgame runs from 2018 to 2023. | data |
| Q16 | Timeline | Why did Thanos collect the Infinity Stones, and what happened when he used them? | To wipe out half of all life, which he believed would save the universe from overpopulation. His snap at the end of Avengers: Infinity War erased half of all living things (the Blip), many heroes among them. | plot text |
| Q17 | Timeline | How did the Avengers reverse the Blip? | They travelled through the Quantum Realm to the past to collect the Infinity Stones (the time heist). Bruce Banner's snap brought everyone back; Tony Stark's snap destroyed Thanos and his army and killed Tony. | plot text |
| Q18 | Timeline | What events led to the multiverse being opened? | Sylvie killed He Who Remains at the end of Loki season 1, so the Sacred Timeline branched into a multiverse. Doctor Strange's spell in Spider-Man: No Way Home pulled in people from other universes, and Multiverse of Madness showed incursions between universes. In Loki season 2, Loki became the keeper of the branching timelines. | plot text |
| Q19 | Identity | Are Loki and Sylvie the same character? | No. Sylvie is a variant of Loki but a separate character; Wikidata marks them as different from each other. | data |
| Q20 | Identity | How many versions of Wolverine are there, and from which universes? | Five Wolverines, all linked as variants: the Fox films' Logan (Earth-10005), Logan's Logan (Earth-17315), the X-Men '97 Wolverine (Earth-92131), and Deadpool & Wolverine's Wolverine and Cavillrine (both unnumbered). X-24, Logan's clone, is linked to them as a variant too. | data |
| Q21 | Identity | Is Captain Carter the same character as Peggy Carter? | No. Captain Carter in Doctor Strange in the Multiverse of Madness is a separate Earth-838 variant of Peggy Carter (Earth-616); What If...? has another variant. Hayley Atwell plays all three. | expert |
| Q22 | Identity | Is the Reed Richards in Avengers: Doomsday the same as the one in Multiverse of Madness? | No. Doomsday's is Pedro Pascal's, from Earth-828 (the same as in The Fantastic Four: First Steps); Multiverse of Madness has John Krasinski's, from Earth-838. | expert |
| Q23 | Identity | Is the Beast in The Marvels the same as in the Fox X-Men films? | Yes: Kelsey Grammer's Beast of Earth-10005, who also appears in Avengers: Doomsday. The X-Men '97 Beast (Earth-92131) is a variant. | expert |
| Q24 | Identity | What other names is Wanda Maximoff known by? | The Scarlet Witch, Glamour and Harbinger of Chaos. | data |
| Q25 | Identity | Which universe is Chris Evans's Johnny Storm from, and is he the same as Joseph Quinn's? | Earth-121698, the universe of the Fox Fantastic Four films (2005 and 2007), where he is the same Johnny Storm. Joseph Quinn's Johnny Storm is a different variant, from Earth-828; Michael B. Jordan's, in Fantastic Four (2015), is another, from Earth-15866. | expert |
| Q26 | Identity | Is the Gambit in Avengers: Doomsday the same as in Deadpool & Wolverine? | Yes. Channing Tatum's Gambit escapes the Void (in a deleted credits scene); his universe has no number. | expert |
| Q27 | Identity | Are May Parker and Maybelle Parker the same character? | Yes: May is short for Maybelle. Marisa Tomei plays her. | expert |
| Q28 | Teams | Who are the members of the Illuminati in Doctor Strange in the Multiverse of Madness? | On Earth-838: Professor X, Captain Carter, Captain Marvel (Maria Rambeau), Black Bolt, Reed Richards and Baron Mordo. Their universe's Stephen Strange founded the team. | data |
| Q29 | Teams | Who has been a member of both the Avengers and the Guardians of the Galaxy? | Thor, Nebula and Rocket. | data |
| Q30 | Teams | Who are the New Avengers (the Thunderbolts)? | Yelena Belova (leader), Bucky Barnes, Alexei Shostakov (Red Guardian), Ava Starr (Ghost), John Walker and Sentry; Valentina Allegra de Fontaine founded the team. | data |
| Q31 | Teams | Who leads the Avengers now, and who led them before? | Sam Wilson leads them now. Earlier leaders were Nick Fury, Steve Rogers, Tony Stark and Natasha Romanoff. | data |
| Q32 | Teams | Who are the Fantastic Four of Earth-828, and do they appear in Avengers: Doomsday? | Reed Richards (leader), Sue Storm, Johnny Storm and Ben Grimm; all four appear in Doomsday. | data |
| Q33 | Teams | Which X-Men of Earth-10005 appear in Avengers: Doomsday? | Charles Xavier, Cyclops, Beast, Nightcrawler, and the former members Magneto and Mystique. | data |
| Q34 | Teams | What happened to the Guardians of the Galaxy at the end of Vol. 3? | The team split up. Rocket leads a new team with Groot, Kraglin, Adam Warlock, Cosmo, Phyla and Blurp; Peter Quill, Drax, Mantis, Nebula and Gamora left. | expert |
| Q35 | Big picture | Which titles are in Phase Four? | WandaVision, The Falcon and the Winter Soldier, Loki season 1, What If...?, Black Widow, Shang-Chi and the Legend of the Ten Rings, Eternals, Hawkeye, Spider-Man: No Way Home, Moon Knight, Doctor Strange in the Multiverse of Madness, Ms. Marvel, Thor: Love and Thunder, I Am Groot, She-Hulk: Attorney at Law, Werewolf by Night, Black Panther: Wakanda Forever and The Guardians of the Galaxy Holiday Special. What If...? and I Am Groot continue into Phase Five. | data |
| Q36 | Big picture | What is the Infinity Saga about? | Phases One to Three, 23 films from Iron Man (2008) to Spider-Man: Far From Home (2019). The Avengers form and face Thanos, who collects the Infinity Stones and erases half of all life; they reverse it in Avengers: Endgame, where Tony Stark dies and Steve Rogers retires. | plot text |
| Q37 | Big picture | Which phase and saga does Avengers: Doomsday belong to? | Phase Six of the Multiverse Saga. | data |
| Q38 | Big picture | How many titles are in each phase? | Phase One 6, Phase Two 6, Phase Three 11, Phase Four 16, Phase Five 11 and Phase Six 7. Four titles span two phases: What If...? and I Am Groot (Four and Five), and Daredevil: Born Again and Your Friendly Neighborhood Spider-Man (Five and Six). | data |
| Q39 | Big picture | Which titles are in no MCU phase? | 37 titles: the 13 Fox X-Men films and X-Men '97; the Marvel Television series Agents of S.H.I.E.L.D., Agent Carter and Inhumans; the six Netflix series (Daredevil, Jessica Jones, Luke Cage, Iron Fist, The Defenders and The Punisher); and the 14 Fox Fantastic Four, Raimi and Webb Spider-Man, and Sony films. | data |
| Q40 | Big picture | Who are the main villains of the Multiverse Saga? | Kang and his variants (He Who Remains, Kang the Conqueror), then Doctor Doom, played by Robert Downey Jr. in Avengers: Doomsday. | plot text |
| Q41 | Analytics | Which title grossed the most? | Avengers: Endgame, about $2.80 billion. | data |
| Q42 | Analytics | Which MCU film grossed the least? | The Marvels, about $206 million. Among all films, The New Mutants, about $49 million. | data |
| Q43 | Analytics | Do sequels earn more than the films before them? | Mostly: 23 of 37 sequels out-grossed the previous film in their Wikidata film series. The 14 exceptions are Avengers: Age of Ultron, Thor: Love and Thunder, Guardians of the Galaxy Vol. 3, Ant-Man and the Wasp: Quantumania, Black Panther: Wakanda Forever, The Marvels, Captain America: Brave New World, X-Men: Apocalypse, Dark Phoenix, Fantastic Four: Rise of the Silver Surfer, Spider-Man 2, The Amazing Spider-Man 2, Venom: Let There Be Carnage and Venom: The Last Dance. (Deadpool & Wolverine counts twice, after Deadpool 2 and after Logan.) | data |
| Q44 | Analytics | Which character appears in the most titles? | Nick Fury (14 titles, including Agents of S.H.I.E.L.D.), then Steve Rogers (12). Stan Lee's cameo character (19) is left out. | data |
| Q45 | Analytics | Which actor appears in the most titles? | Stan Lee, 36 titles, all cameos. Not counting cameos, Samuel L. Jackson and Chris Evans (15 each). | data |
| Q46 | Analytics | Which character shares films with the most other characters? | Steve Rogers (239 characters), then Nick Fury (223) and Thor (201), leaving out Stan Lee's cameo character. | data |
| Q47 | Analytics | Which film had the biggest budget? | Avengers: Infinity War, $400 million. | data |
| Q48 | Analytics | What is the average TMDB rating of the films in each phase? | Phase One 7.11, Phase Two 7.23, Phase Three 7.47 (the highest), Phase Four 7.11, Phase Five 6.81 and Phase Six 7.70 (two released films); films outside the phases 6.58. | data |
| Q49 | Analytics | How old was Robert Downey Jr. when Iron Man was first released? | 43: born on 4 April 1965; Iron Man was first released on 30 April 2008. | data |
| Q50 | Analytics | Which title has the highest TMDB rating? | X-Men '97 (8.70). Among films, Spider-Man: Brand New Day (8.46), then Avengers: Infinity War (8.25) and Avengers: Endgame (8.20). | data |

## Data gaps found while writing the answers

- Captain America: Brave New World has no box office on Wikidata (TMDB: about $415 million).
- The Avengers team lists have no T'Challa or Doctor Strange. (Nick Fury as the only founder
  is right, per the MCU expert.)
- Stan Lee's cameos are one character, "Watcher Informant", which skews the counts in Q44
  to Q46; the schema should mark cameos.
- Iron Man's first release is 30 April 2008 in both Wikidata and TMDB; its Sydney premiere
  was 14 April 2008, which neither source has.
- Wikidata does not link Black Panther: Wakanda Forever to Black Panther as its sequel; Q43
  counts it anyway.
- Wikidata dates Jessica Jones (all season 1 episodes) 20 October 2015, without a source. The
  first release used is the verified New York premiere, 17 November 2015 (Netflix release
  20 November); Luke Cage's is its Harlem premiere, 28 September 2016 (docs, "Verified first
  releases").
