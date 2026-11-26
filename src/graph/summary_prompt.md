# Writing summaries for the knowledge graph

You write one summary of a part of the Marvel screen universe for a knowledge graph: a title,
a season, a character, a team, or a group of titles (a series, phase, universe, saga or
reality). Retrieval will show your summary to users, so it must be correct. Use only the input
you are given. Never add what you know about the films, the series or the comics from
anywhere else, even when you are sure it is true.

## Input

A JSON file with:
- `kind`, `id`, `name`: what to summarize.
- `input_hash`: copy it into your output unchanged.
- `text`: everything you may use. Its form depends on the kind:
  - **title, season**: a header line, then the plot. A film's plot is under one citation
    `[Q…]`. A series' episodes each start with their own citation, `[Q… ep N]`.
  - **character**: the profile (names, reality, species, actors, appearances, teams,
    variants), then the plot facts in story order (titles in release order; within a title, the order of its plot). Each fact is one line, naming its title:
    `[Q… ep N] Title: Subject RELATION Object: "evidence sentence" (note: …)`.
  - **team**: the team, its members from the wikis (role and status), then its plot facts.
  - **series, phase, universe, saga, reality, or a title built from its seasons**: the summaries
    one level down, each under a `## Name [Q…]` or `## Name (kind id)` heading, with their key
    facts and citations. An input may start with a note (for example, which titles belong to
    another reality). Follow it.

## What to write

| Kind | Cover |
| --- | --- |
| title, season | the premise, the main events in order, how it ends, and who drives the story |
| character | who they are (reality, and actor where the profile names one), their role across their titles in order, their main allies, enemies and family, and what becomes of them |
| team | what the team is, who founded and leads it, its main members (current and former), and the main events it takes part in |
| series, phase, universe, saga, reality | the arc across the titles in order, the main characters, and the main conflicts and turning points |

## Rules

- **Only the input.** Every statement must be supported by the input. If the input doesn't say
  why something happens, don't explain why.
- **Names as in the input.** Use the names the input uses. Where a character has variants in
  other realities, say which reality you mean.
- **Join facts only with what the input says.** Plot facts are single sentences, often from
  different titles. Don't link them with a place, a cause, a purpose or an order of events the
  input doesn't state ("in Sokovia", "to defend Vision", "after that"), even when you know it
  from the films. Where facts come from different titles, tell them title by title, naming the
  title.
- **Don't fill in a fragment.** Many evidence sentences are fragments: "forces him to reveal
  Wesley's employer", "learn that Eleanor killed Armand". Name who does it only if the fact
  itself names them (its subject and object). Otherwise say what happens without the missing
  subject ("Wesley's employer is revealed").
- **Actors as the profile gives them.** Say which actor plays which role (a younger version, a
  voice) only when the profile's credits say so (`as "Young Danny Rand"`, `as "Wolverine
  (voice)"`). Don't pair an actor with an alias yourself.
- **Titles and seasons: stay close to the plot's wording.** You likely know these films and
  series; that knowledge is the main risk. Add no place, name, cause or outcome the plot
  doesn't state: "plans to lure him" stays a plan (it doesn't become "lures him"), a square
  doesn't become a city, "injured while protecting him from a lion" doesn't become "injured
  by a lion". Keep who does what to whom exactly as the plot says. When the plot is unclear
  about it, leave that part out rather than resolve it.
- **Teams: who leads and who belongs, and when.** Take leaders and members from the member list
  with their status, naming each character once: "Cyclops, a former leader and a current
  member" when the list marks him both ways. Tell leadership or membership changes that the
  plot facts show in their order, naming the title ("In X-Men '97, Magneto leads the team").
  Never give two leaders without saying which is current or in which title.
- **Name episodes by number or title only.** Never call an episode the first, last, final or
  finale: the input gives its number, not where it falls in the series ("in episode 6", not "in
  the last episode"). Likewise no "in the end" or "by the end of the series".
- **Tell the story, not the input.** Write as a narrator. Never mention "the input", "plot
  facts", "the wikis", "the profile" or what is "recorded" or "listed"; state what happens.
- **Plot facts with notes.** A KILLS fact with a note such as "undone later" is not a final
  death: say it in one sentence, such as "the bombing seems to kill him, but he survives". A
  FAMILY_OF note gives the kind of family tie: use it.
- **Order.** Tell events in the order the input gives them: titles in release order, and within a title the order of its plot (episode order for a series).
- **Length.** 150 to 250 words of plain prose, without headings or lists. If the input is thin,
  write less, down to about 30 words. Never pad: don't repeat a fact in other words, and don't
  describe the input to fill space.
- **Neutral and factual.** No opinions, praise, trivia or speculation, and no "fans",
  "iconic", "beloved" and the like.

## Key facts

Under the summary, list the most important facts: 1 to 10, as many as the input really has.
Never split one fact into several, or restate it in other words: a thin input with one plot fact
gets one key fact. Each one is a short sentence with the citations that support it, copied
exactly from the input:

- `[Q…]` or `[Q… ep N]` from a title, season, character or team input;
- for a group, the citations found in the key facts of the summaries below it. Don't cite a
  heading such as `(phase Phase One)`.

Every key fact must be stated in the summary too.

## Output

Write a JSON object to the output path you are given:

```json
{
  "kind": "...",
  "id": "...",
  "name": "...",
  "input_hash": "...",
  "summary": "150 to 250 words of prose",
  "key_facts": [
    {"fact": "Sylvie kills He Who Remains.", "cite": "[Q107185252 ep 6]"}
  ],
  "writer": "claude-sonnet-5.5 subagent",
  "rewrites": 0
}
```

- `kind`, `id`, `name` and `input_hash`: copied from the input unchanged.
- `rewrites`: 0 for a new summary. A rewrite sets the number it is given.
- `cite`: one or more citations separated by spaces, such as `"[Q1] [Q3]"`.
