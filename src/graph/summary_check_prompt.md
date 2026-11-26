# Checking a summary against its input

You check one summary written for a Marvel knowledge graph. Another agent wrote it from an
input, using only that input. Your job is to find every statement the input does not support.
You did not write the summary, so read it critically. Judge only by the input. Never by what
you know about the films, the series or the comics, even when the statement is true.

## Input

Two JSON files:
- the **input**: `kind`, `id`, `name`, `input_hash` and `text`. The text is everything the
  writer was allowed to use (see src/graph/summary_prompt.md for its form);
- the **summary**: `summary` (prose) and `key_facts` (`fact` and `cite`).

## What to check

1. Split the summary into its statements: each claim of fact, usually one per clause. Add each
   key fact as a statement of its own.
2. For each statement, decide whether the input supports it:
   - **supported**: the input states it, or it follows directly from what the input states.
     Ordering events as the input orders them, or calling a fact's subject an ally when the
     input has an ALLY_OF fact, counts as supported.
   - **unsupported**: the input doesn't say it, says something else, or the statement adds a
     reason, a motive, a time or a detail the input lacks. A death the input marks as "undone
     later", told as final, is unsupported.
3. For each key fact, also check that its `cite` names citations that appear in the input and
   that support the fact.
4. Look hardest at the words that join two facts. A place ("in Sokovia"), a purpose ("to
   defend Vision", "to save"), a cause ("because", "so") or an order ("after", "then") that the
   input doesn't state is unsupported, even when the two facts themselves are in the input.
   This is the error checkers have missed most often.
5. Check the names. A character, team, place or title the input doesn't mention is
   unsupported, and so is a wrong reality for a character with variants.

Be strict but fair. A statement that merely words the input differently is supported. **When
in doubt, mark it unsupported**, with the reason: a doubtful pass lets an error through for good,
while a doubtful fail only costs a rewrite.

6. In a title or season digest, compare each event with the plot sentence it comes from: the
   same actors, the same object (who is carried, who is injured, by what), the same outcome (a
   plan is not a success), and no place or name the plot doesn't give. Writers know these films;
   anything from outside the plot is unsupported.
7. In a team summary, a leader or member must have the status the member list gives (current,
   former), or a cited plot fact with its title. Mark as unsupported a sentence that names a
   leader without its status or title when the summary names another leader too.
8. Mark as unsupported any sentence that talks about the input instead of the story, such as
   "the input notes", "is recorded as" or "in one plot fact". The summary must state what
   happens. Give the reason "talks about the input".
9. Mark as unsupported a key fact that only restates another key fact, or splits one fact into
   two. Give the reason "padding".
10. Check who does what. A statement that names who acts where the evidence is a fragment
   without that subject ("learn that ...", "forces him to ..."), and the fact's own subject and
   object don't name them either, is unsupported. So is an actor paired with a role (a young
   version, a voice) that the profile's credits don't give.

## Output

Write a JSON object to the output path you are given:

```json
{
  "kind": "...",
  "id": "...",
  "input_hash": "...",
  "statements": [
    {"text": "Sylvie kills He Who Remains.", "supported": true, "reason": ""},
    {"text": "She does it to free the multiverse.", "supported": false,
     "reason": "the input gives no motive"}
  ],
  "verdict": "pass",
  "checker": "claude-sonnet-5.5 subagent"
}
```

- `kind`, `id` and `input_hash`: copied from the input unchanged.
- `reason`: empty when supported. Otherwise one short line saying what the input lacks or
  says instead.
- `verdict`: `"pass"` when every statement is supported, else `"fail"`.
