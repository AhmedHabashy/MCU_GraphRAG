# Fact extraction with Claude Code subagents

How the plot facts in `processed_data/extraction/plots/` were extracted, so a run can be
repeated exactly. The extraction rules themselves (relations, linking, output format) are in
[src/graph/extraction_prompt.md](../src/graph/extraction_prompt.md); this file holds the
commands and the prompt each agent was given.

## Setup

- **Agents:** Claude Code subagents of type `general-purpose`, model **Sonnet 5.5**
  (`model: "sonnet"` on the Agent tool), launched from the main Claude Code session.
- **Work unit:** a *chunk* = one film plot, or a group of whole episode summaries of one
  series (at most 25,000 characters). An agent gets a *batch* of chunks, about 40,000
  characters of text.
- **Parallelism:** batches were run in waves of 13 agents.

## Commands

Run from the project root.

```powershell
# 1. Build the chunk inputs (cast, teams, text) and list the pending chunks per agent batch.
.venv\Scripts\python.exe -m src.graph.prepare_extraction
#    -> processed_data/extraction/plots/inputs/<chunk>.json
#    -> processed_data/extraction/plots/batches.json   ([[chunk, ...], ...], one list per agent)

# 2. Launch one agent per batch with the prompt below (from the main Claude Code session).

# 3. Check every output after the agents finish.
.venv\Scripts\python.exe -m src.graph.check_extraction
#    "111 chunks, 3552 facts, 0 chunks with problems: []" on the first full run
```

A chunk is pending only when its output is missing or older than its input, and an input is
rewritten only when its content changes, so rerunning step 1 lists only new or changed text.
If inputs change but the outputs still pass `check_extraction` against them (e.g. only wrong
aliases were removed from a cast), the outputs may be accepted as current by touching them;
this was done once (46 chunks, after the voice-actor alias fix) and is recorded in the commit
history.

## Agent prompt

Each agent got this prompt, with `<CHUNK IDS>` replaced by one batch from `batches.json`
(space-separated):

```text
You are a fact-extraction agent for a Marvel knowledge graph. Project folder: D:\_study\MCU_graphRAG

1. Read the instructions in D:\_study\MCU_graphRAG\src\graph\extraction_prompt.md and follow them exactly.
2. Process these chunks, one at a time: <CHUNK IDS>
   For each chunk ID:
   - input:  D:\_study\MCU_graphRAG\processed_data\extraction\plots\inputs\<ID>.json  (read it with the Read tool)
   - output: D:\_study\MCU_graphRAG\processed_data\extraction\plots\outputs\<ID>.json  (write it with the Write tool)
   - check it by running exactly this one command, from D:\_study\MCU_graphRAG:
     .venv\Scripts\python.exe -m src.graph.check_extraction processed_data\extraction\plots\inputs\<ID>.json processed_data\extraction\plots\outputs\<ID>.json
     If it reports problems, fix the output with Write/Edit and check again until it reports 0 facts with problems.
3. Use only the Read, Write and Edit tools and that check command. Do not run Python or any other command yourself, and do not edit any other file.

When done, reply in one or two lines: facts per chunk, and anything in the instructions you found unclear.
```

The first wave used the same prompt with a shorter step 3 ("Do not edit any other file and
run no other command."); two agents then ran small Python snippets of their own, so the
second wave got the stricter wording above. Agents still sometimes ran the check in a shell
loop; the final full check is what counts.

## Pilot prompt

The pilot (Deadpool & Wolverine and Loki season 1, before the full run) gave each agent one
input and one output path and only the Read and Write tools:

```text
You are a fact-extraction agent for a Marvel knowledge graph.

1. Read the instructions in D:\_study\MCU_graphRAG\src\graph\extraction_prompt.md and follow them exactly.
2. Input file: <input.json>
3. Write your output JSON to: <output.json>

Do not edit any other file and do not run scripts. Use only the Read and Write tools. When done, reply with one line: the number of facts written, and any instruction you found unclear.
```

## What the agents' replies changed

The agents' "unclear" notes led to these changes, all now in the extraction prompt or the code:

- Unlinked subjects and groups (the Time-Keepers, the Salem Seven) are allowed, with one
  consistent name; one sentence may support several facts.
- `title_qid` is the title's QID, also for a series split into parts; `episode` is the
  number after "Episode" (numbered across the whole series).
- The TVA was added to the teams table.
- Wrong cast aliases reported for X-Men '97 led to the voice-actor fix in
  `build_characters` (a credit links to an actor's only Wikidata role only when it names it).

## Results of the first full run (2026-11-20)

- 111 chunks from 98 titles, 26 agent batches in 2 waves, 3,552 facts, 0 check problems.
- About 75k to 170k tokens and 1 to 5 minutes per agent.
- Subject linked in 92% of facts, both ends in 68%.
