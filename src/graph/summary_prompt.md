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
    variants), then the plot facts in release order. Each fact is one line:
    `[Q… ep N] Subject RELATION Object: "evidence sentence" (note: …)`.
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
- **Plot facts with notes.** A KILLS fact with a note such as "undone later" is not a final
  death: say so. A FAMILY_OF note gives the kind of family tie: use it.
- **Order.** Tell events in the order the input gives them (release order, episode order).
- **Length.** 150 to 250 words of plain prose, without headings or lists. If the input is thin,
  write less, down to about 60 words. Never pad.
- **Neutral and factual.** No opinions, praise, trivia or speculation, and no "fans",
  "iconic", "beloved" and the like.

## Key facts

Under the summary, list the 3 to 10 most important facts. Each one is a short sentence with
the citations that support it, copied exactly from the input:

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
  "writer": "claude-sonnet-5.5 subagent"
}
```

- `kind`, `id`, `name` and `input_hash`: copied from the input unchanged.
- `cite`: one or more citations separated by spaces, such as `"[Q1] [Q3]"`.
