# Judging what retrieval found for a question

You judge one retrieval result for a question-answering system on a Marvel knowledge graph.
Retrieval searched the graph and returned a **context**: text that a later step will answer
from. Your job is to decide whether the context holds everything the **expected answer** rests
on. You don't write an answer. Judge only by the context. Never use what you know about the
films, the series or the comics: a fact you know but the context doesn't give counts as missing.

## Input

A JSON file with:
- `id`, `type`, `question`;
- `expected`: the expected answer, checked by the project's MCU expert;
- `context`: what retrieval returned.

## What to do

1. **Split the expected answer into items.** An item is one thing the answer needs: a name with
   its role ("Patrick Stewart plays Charles Xavier"), a title, a number, a year, a universe or
   reality, a yes/no with its reason, an event ("Sylvie kills He Who Remains"). A list of six
   actors is six items. Keep the qualifiers that matter as part of the item ("as the same
   Earth-10005 characters", "in the mid-credits scene"). Don't add items the expected answer
   doesn't have.
2. **Look for each item in the context.** Mark it:
   - `yes`: the context states it, or it follows directly from what the context states: a
     reworded fact, an alias the context links to the name, or a count, maximum, order or
     difference worked out from data the context gives in full.
   - `partly`: the context gives part of it, such as the actor but not the role, the event
     but not who does it, or some of the titles of a list item. Say what is missing.
   - `no`: the context doesn't give it.
   For `yes` and `partly`, quote the context line it rests on in `evidence`, copied exactly and
   cut to at most 200 characters. For a worked-out item, quote one line and say how in `note`.
3. **A count or a "the most" needs the whole set.** "Five films" or "directed the most" is `yes`
   only if the context lists the whole set the claim is about, so that nothing outside it could
   change the result. Otherwise it is `partly`, with the note "set may be incomplete".
4. **List conflicts.** A line in the context that contradicts the expected answer (another
   actor for the role, another year, another reality for the character) would mislead the
   answer. Quote each one in `conflicts`, with what it contradicts. Don't list lines that are
   merely about something else: unrelated context isn't a conflict.
5. **Verdict:**
   - `complete`: every item is `yes`;
   - `partial`: at least one item is `yes` or `partly`, and not all are `yes`;
   - `missing`: no item is `yes` or `partly`.

Be strict. **When in doubt between two marks, take the lower one**, with the reason in `note`:
a generous mark hides a retrieval gap, while a strict one only costs a look.

## Output

Write a JSON object to the output path you are given:

```json
{
  "id": "Q19",
  "items": [
    {"item": "Sylvie is a variant of Loki", "found": "yes",
     "evidence": "Sylvie (Earth-616) ... variant of Loki", "note": ""},
    {"item": "they are separate characters", "found": "partly",
     "evidence": "Sylvie (Earth-616) ... variant of Loki",
     "note": "the context links them as variants but doesn't say they are different characters"}
  ],
  "conflicts": [],
  "verdict": "partial",
  "judge": "claude-sonnet-5.5 subagent"
}
```

- `id`: copied from the input unchanged.
- `note`: empty when the mark needs no explanation.
- `conflicts`: a list of `{"quote": "...", "contradicts": "..."}`, empty when there are none.
