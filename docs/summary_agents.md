# Summaries with Claude Code subagents

This runbook explains how the summaries in `processed_data/summaries/` are written and checked,
so that a run can be repeated exactly. The design and the decisions are in
[rag_design.md](rag_design.md), under "Summaries". The rules for the agents are in
[src/graph/summary_prompt.md](../src/graph/summary_prompt.md) (writers) and
[src/graph/summary_check_prompt.md](../src/graph/summary_check_prompt.md) (checkers).

## Setup

- **Agents:** Claude Code subagents of type `general-purpose` on **Sonnet 5.5**
  (`model: "sonnet"` on the Agent tool), launched from the main Claude Code session.
- **Work unit:** one summary. An agent gets a **batch** of summaries: about 60,000 characters of
  input in all, and at most 20 summaries (`BATCH_CHARS` and `BATCH_ITEMS` in
  `src/graph/summary_inputs.py`). Wave 1 had no item cap: an agent given 43 small summaries
  took over 11 minutes and also wrote two other batches by mistake.
- **Parallelism:** batches run in waves of up to 10 agents.
- **Levels:** level 1 (titles, seasons, main characters, teams) is written and kept first. The
  inputs are then rebuilt: the 3 split titles, then series, phases and universes (level 2), then
  sagas and realities (level 3) become buildable in turn. Each level runs the same loop.

## The life of a summary

```
write ──► automatic check (the writer fixes it) ──► check 1 ──pass──► check 2 ──pass──► KEPT
                                                      │fail             │fail
                                                      ▼                 ▼
                                              rewrite (from the failing check's reasons)
                                              ── after 2 rewrites that still fail: FLAGGED for the user
```

- A check is done by a **new** checker agent each time, never by the writer. A summary is kept
  only when **two checks in a row** pass the same version of it. Checkers vary, so one may miss
  what another finds.
- A rewrite clears both checks: the new version needs two passing checks of its own.
- A summary that still fails after its second rewrite is **flagged**. It is left for the user
  to review, and nothing builds on it until the user decides.
- A summary becomes pending again when its input changes (a new `input_hash`).

## Files

```
processed_data/summaries/
  inputs/<kind>/<id>.json            what the writer may use (src/graph/summary_inputs.py)
  outputs/<kind>/<id>.json           the summary; "rewrites" counts its rewrites (0 at first)
  checks/<kind>/<id>.check1.json     check 1 of the current version
  checks/<kind>/<id>.check2.json     check 2 of the current version
  status.json                        every summary's state, and the batches for each next action
```

A check counts only if it is newer than the summary it checked. A rewritten summary is newer
than its old checks, so they no longer count. A check must also list at least as many
statements as the summary has key facts, since each key fact is a statement of its own. In wave
3, a checker lumped them into one statement, and its 20 checks were discarded.

**Reviews.** Two passing checks can still miss an error. In wave 3, both checks passed "is
consoled by her angrily", but in the input it is Fisk who is angry. So the user, or the main
session reading summaries, can file a review: `reviews/<kind>/<id>.json`, the same shape as a
check, with `"verdict": "fail"` and the unsupported statements with their reasons. A review
newer than the summary sends it to a rewrite, even if it was kept, and the rewrite then needs
two new checks.

## The status script (to build)

`src/graph/summary_status.py` reads the inputs, outputs and checks, and gives each summary one
state:

| State | When | Next action |
| --- | --- | --- |
| `write` | no output, or the output is for another `input_hash` | writer |
| `fix` | the automatic check reports a problem | writer |
| `check1` | no check 1 newer than the output | checker |
| `check2` | check 1 passed, and no check 2 newer than the output | checker |
| `rewrite` | a review fails it, or the newest check failed; and `rewrites` < 2 | writer, with the reasons |
| `flagged` | the same, but `rewrites` = 2 | the user |
| `kept` | checks 1 and 2 both passed, both newer than the output | none |

It writes `status.json` with the counts per state and per kind, and the batches for each next
action. It also prints the counts. Its tests cover each state and the "newer than" rule.

## Commands

Run from the project root.

```powershell
# 0. Graph, profiles and inputs current (Neo4j running):
.venv\Scripts\python.exe -m src.graph.profiles
.venv\Scripts\python.exe -m src.graph.summary_inputs

# 1. See what to do next:
.venv\Scripts\python.exe -m src.graph.summary_status
#    -> counts per state; processed_data/summaries/status.json holds the batches per action

# 2. Freeze the wave's batches, so a later status run can't move them under running agents:
copy processed_data\summaries\status.json processed_data\summaries\wave<N>.json
#    Launch one agent per batch of the next action (write, check1, check2, rewrite), up to 10
#    at once, with the prompts below. Each agent reads its own batch from wave<N>.json
#    ("actions" -> action -> index). Repeat 1 and 2 until no summary is in write, fix, check1,
#    check2 or rewrite.

# 3. When the level is kept, rebuild the inputs: the next level becomes buildable.
.venv\Scripts\python.exe -m src.graph.summary_inputs

# 4. Show the user every flagged summary, with its input, its summary and the failing check.
```

## Agent prompts

### Writer

Each writer gets this prompt. `<N>` is the wave and `<I>` its batch index under `"write"` (or
`"fix"`).

```text
You are a summary-writing agent for a Marvel knowledge graph. Project folder: D:\_study\MCU_graphRAG

1. Read the instructions in D:\_study\MCU_graphRAG\src\graph\summary_prompt.md and follow them exactly.
2. Your batch is the list at "actions" -> "write" -> index <I> in D:\_study\MCU_graphRAG\processed_data\summaries\wave<N>.json (read it with the Read tool). Each entry has "kind" and "file". Write these summaries, one at a time:
   For each entry:
   - input:  D:\_study\MCU_graphRAG\processed_data\summaries\inputs\<kind>\<file>  (read it with the Read tool)
   - output: D:\_study\MCU_graphRAG\processed_data\summaries\outputs\<kind>\<file>  (write it with the Write tool; set "rewrites": 0)
     If an older output exists there, ignore it and write a new one from the input.
   - check it by running this command once for each summary, from D:\_study\MCU_graphRAG (in PowerShell; a loop over your own files is fine):
     .venv\Scripts\python.exe -m src.graph.check_summaries processed_data\summaries\inputs\<kind>\<file> processed_data\summaries\outputs\<kind>\<file>
     If it reports a PROBLEM, fix the output with Write/Edit and check again until it reports 0 with problems.
     A WARNING lists names the input never mentions: remove such a name unless the input does support it.
   Write only the entries of your own batch. Treat each summary on its own: never carry facts from one input into another summary.
3. Use only the Read, Write and Edit tools and that check command. Do not run Python or any other command yourself, and do not edit any other file.

When done, reply with: how many summaries you wrote, any you could not finish, and anything in the instructions you found unclear. Keep it short.
```

### Checker

`<C>` is 1 or 2: the action is `"check<C>"`, with batch index `<I>` in `wave<N>.json`.

```text
You are a summary-checking agent for a Marvel knowledge graph. Project folder: D:\_study\MCU_graphRAG

1. Read the instructions in D:\_study\MCU_graphRAG\src\graph\summary_check_prompt.md and follow them exactly.
2. Your batch is the list at "actions" -> "check<C>" -> index <I> in D:\_study\MCU_graphRAG\processed_data\summaries\wave<N>.json (read it with the Read tool). Each entry has "kind" and "file". Check these summaries, one at a time:
   For each entry (<stem> is the file name without .json):
   - input:   D:\_study\MCU_graphRAG\processed_data\summaries\inputs\<kind>\<file>
   - summary: D:\_study\MCU_graphRAG\processed_data\summaries\outputs\<kind>\<file>
   - write your result to: D:\_study\MCU_graphRAG\processed_data\summaries\checks\<kind>\<stem>.check<C>.json
   Judge each summary only against its own input.
3. Use only the Read and Write tools. Do not run any command, and do not edit any other file.

When done, reply with one line per summary: the verdict, how many statements, and how many unsupported.
```

### Rewriter

Its batch, `"rewrite"` index `<I>` in `wave<N>.json`, has entries with `kind`, `file`, `check`
(the failing check or review, as a path under `processed_data\summaries\`) and `rewrites` (the
new rewrite count, the old one plus 1).

```text
You are a summary-writing agent for a Marvel knowledge graph. Project folder: D:\_study\MCU_graphRAG
Independent checkers failed some summaries; you fix them.

1. Read the instructions in D:\_study\MCU_graphRAG\src\graph\summary_prompt.md and follow them exactly.
2. Your batch is the list at "actions" -> "rewrite" -> index <I> in D:\_study\MCU_graphRAG\processed_data\summaries\wave<N>.json (read it with the Read tool). For each entry (kind, file, check, rewrites):
   - read the input (processed_data\summaries\inputs\<kind>\<file>), the summary
     (processed_data\summaries\outputs\<kind>\<file>) and the failing check
     (processed_data\summaries\<check>);
   - fix or remove every statement the check marks "supported": false, using only what the
     input says, in the summary and in key_facts. Keep everything else. Set "rewrites" to the
     entry's rewrites;
   - run the check command (as for writers) until it reports 0 with problems.
3. Use only the Read, Write and Edit tools and that check command.

When done, reply with one line per summary: what you changed.
```

## Expected size of a run

These numbers are from the pilot, so they are rough. Level 1 is 507 summaries in about 30
batches.

| Action | Agent runs |
| --- | --- |
| Write | about 30 |
| Check 1 and check 2 | about 60 |
| Rewrites and their checks | depends on how many fail. In pilot round 1, 4 of 5 first drafts failed; in round 2, 0 of 3 did. Somewhere between 10 and 60 runs |
| **Level 1 in all** | **about 100 to 150 runs** |
| Levels 2 and 3 (41 summaries) | about 10 to 20 more |

The run is done one wave at a time, and stopped after the first wave so its results can be
reviewed before the rest is launched.
