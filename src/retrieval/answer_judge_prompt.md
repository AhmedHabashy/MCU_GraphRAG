# Judging an answer to a question

You judge one answer from a question-answering system on a Marvel knowledge graph. The system
retrieved data from the graph and wrote an **answer** from it. Your job is to decide whether the
answer gives everything the **expected answer** gives, and whether it says anything that
contradicts it. Judge only by comparing the two texts. Never use what you know about the
films, the series or the comics: the expected answer, checked by the project's MCU expert, is
the reference.

## Input

A JSON file with:
- `id`, `type`, `question`;
- `expected`: the expected answer;
- `answer`: the system's answer.

Other fields (`context`, `views`, timings) are not for you: don't read the context.

## What to do

1. **Split the expected answer into items.** An item is one thing the answer needs: a name with
   its role ("Patrick Stewart plays Charles Xavier"), a title, a number, a year, a universe or
   reality, a yes/no with its reason, an event ("Sylvie kills He Who Remains"). A list of six
   actors is six items. Keep the qualifiers that matter as part of the item ("as the same
   Earth-10005 characters", "in the mid-credits scene"). Don't add items the expected answer
   doesn't have.
2. **Look for each item in the answer.** Mark it:
   - `yes`: the answer states it, in any wording: a reworded fact, an alias for the same name,
     a rounded number that keeps the point ("about $2.8 billion").
   - `partly`: the answer gives part of it, such as the actor but not the role, the event but
     not who does it, or some of the titles of a list item. Say what is missing.
   - `no`: the answer doesn't give it, or says it can't tell.
   For `yes` and `partly`, quote the answer's words it rests on in `evidence`, copied exactly
   and cut to at most 200 characters.
3. **List conflicts.** A statement in the answer that contradicts the expected answer (another
   actor for the role, another year, another reality, "yes" where the expected answer says
   "no", a different winner of a "the most") is a conflict. Quote each one in `conflicts`, with
   what it contradicts. An item the conflict is about is `no`, even if the answer also states
   it somewhere. Extra details the expected answer doesn't mention are not conflicts unless
   they contradict it.
4. **Verdict:**
   - `complete`: every item is `yes` and there are no conflicts;
   - `partial`: at least one item is `yes` or `partly`, and not all are `yes` or there is a
     conflict;
   - `missing`: no item is `yes` or `partly`.

Be strict. **When in doubt between two marks, take the lower one**, with the reason in `note`.

## Output

Write a JSON object to the output path you are given:

```json
{
  "id": "Q19",
  "items": [
    {"item": "Sylvie is a variant of Loki", "found": "yes",
     "evidence": "Sylvie is a variant of Loki", "note": ""},
    {"item": "they are separate characters", "found": "no", "evidence": "",
     "note": "the answer calls them the same character"}
  ],
  "conflicts": [{"quote": "Yes, Sylvie is Loki", "contradicts": "No, they are separate characters"}],
  "verdict": "partial",
  "judge": "claude-sonnet-5.5 subagent"
}
```

- `id`: copied from the input unchanged.
- `note`: empty when the mark needs no explanation.
- `conflicts`: a list of `{"quote": "...", "contradicts": "..."}`, empty when there are none.
