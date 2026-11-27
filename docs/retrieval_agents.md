# Judging retrieval with Claude Code subagents

This runbook explains how a retrieval run is judged, so that it can be repeated exactly. The
design is in [rag_design.md](rag_design.md), under "How we judge retrieval". The judges' rules
are in [src/retrieval/judge_prompt.md](../src/retrieval/judge_prompt.md).

## Setup

- **Agents:** Claude Code subagents of type `general-purpose` on **Sonnet 5.5**
  (`model: "sonnet"` on the Agent tool), launched from the main Claude Code session.
- **Work unit:** one question. A judge gets a **batch**: about 60,000 characters of context
  and expected answers in all (`JUDGE_BATCH_CHARS` in `src/retrieval/evaluation.py`).
- **Parallelism:** up to 10 judges at a time.

## A run

1. `python -m src.retrieval.evaluation run <strategy>` writes
   `processed_data/retrieval/eval/<strategy>/<run>/`: `Q01.json` to `Q50.json` (the question, the
   expected answer, the context, the retrieval time) and `batches.json`.
2. Each judge is told the run folder and its batch number, and writes `<id>.judge.json` beside
   each question file. It judges only from the context, never from what it knows.
3. `python -m src.retrieval.evaluation report <run folder>` writes `report.md`: verdicts per
   question type and per question, the items not found, and the timings. Questions without a
   valid judgement are listed as not judged.
4. The main session reads the gaps before anything is changed: a miss is traced to retrieval,
   to the judge, or to the expected answer.

## Calibration

Before the first run, two judges each scored the same eight contexts built from the graph, with
verdicts known in advance (complete, partial, missing, an incomplete set, a planted conflict,
noise around the answer). The result is in rag_design.md, under "How we judge retrieval".
