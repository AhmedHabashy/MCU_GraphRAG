# Fact extraction from plot text (pilot draft)

You extract facts about the Marvel screen universe from one title's plot or episode
summaries, for a knowledge graph. Use only the text you are given: never add what you know
about the films or comics from elsewhere.

## Input

A JSON file with:
- `title`, `title_qid`: the film or series season.
- `cast`: the title's characters, each with `id`, `label`, `reality`, `actor` and `aliases`.
- `teams`: team and organization IDs already in the graph (e.g. `Avengers@Earth-616`).
- `text`: the plot (films) or the episode summaries ("Episode N: title" then its summary).

## What to extract

One fact per relationship stated or directly shown in the text, between characters, or
between a character and a team, organization, place, object or event.

Relations (use exactly these names):

| Relation | Meaning |
| --- | --- |
| ALLY_OF | works with, helps, fights alongside |
| ENEMY_OF | opposes, fights against, hunts |
| KILLS | kills (also when undone later; say so in `note`) |
| RESCUES | saves, frees, resurrects |
| FAMILY_OF | parent, child, sibling, spouse; put the kind in `note` |
| ROMANCE_WITH | a romantic relationship |
| MEMBER_OF | belongs to a team or organization |
| WORKS_FOR | is employed by, serves, obeys a person or organization |
| LEADS | leads a team, organization or group |
| VARIANT_OF | is another version of the same character |
| IMPERSONATES | poses as someone else |
| POSSESSES | has, steals, uses or is given an object (Tesseract, TemPad, ...) |
| TRAVELS_TO | goes to a place, time or universe |
| CREATES | builds, founds or causes something |

## Linking entities

- A character in `cast`: put its `id` in `subject_id` / `object_id`. Match by label, alias
  or the context (e.g. "Wade" is Wade Wilson). If two cast entries could fit, pick the one whose
  `reality` fits the scene and say why in `note`.
- A team or organization in `teams`: put its ID.
- Anything else (a character missing from `cast`, a place, object or event): leave the ID
  empty and give the name only. Never invent an ID.

## Output

Write a JSON object to the output path you are given:

```json
{
  "title_qid": "...",
  "facts": [
    {
      "subject_id": "...", "subject_name": "...",
      "relation": "ALLY_OF",
      "object_id": "", "object_name": "...", "object_type": "character|team|organization|place|object|event|time|universe",
      "episode": null,
      "evidence": "an exact quote from text, copied character for character",
      "note": ""
    }
  ]
}
```

Rules:
- `evidence` must be copied exactly from `text` (one sentence or less). It is checked by
  string search, so do not fix typos, change quotes or join sentences.
- `episode`: the episode number for series, `null` for films.
- No duplicate facts: the same subject, relation and object once per episode (once for a film).
- Prefer fewer, correct facts over many uncertain ones.
