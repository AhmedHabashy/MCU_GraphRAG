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
2. **Two judges per batch**, each a new agent: judge 1 writes `<id>.judge1.json` and judge 2
   `<id>.judge2.json` beside each question file. Each is told the run folder, its batch number
   and its judge number, and judges only from the context, never from what it knows. Neither
   sees the other's files.
3. `python -m src.retrieval.evaluation report <run folder>` writes `report.md`: verdicts per
   question type and per question, the items not found, the questions the judges disagree
   on, and the timings. **The lower of the two verdicts counts.** A question lacking a valid
   judgement from either judge is listed as not judged.
4. The main session reads the gaps before anything is changed: a miss is traced to retrieval,
   to the judge, or to the expected answer.

## An answer run

The same, with the answer step on top (rag_design.md, "The answer step"):

1. `python -m src.retrieval.evaluation answer <local|global|drift>` writes
   `processed_data/retrieval/eval/answers/<strategy>/<run>/`. Each question file also holds the
   `answer`, the `views` the model called, and `retrieval_seconds` and `answer_seconds`;
   `"judged": "answer"` marks it. Batches are about 5,000 characters
   (`ANSWER_BATCH_CHARS`), as answers are short.
2. Two judges per batch, as above, following
   [src/retrieval/answer_judge_prompt.md](../src/retrieval/answer_judge_prompt.md): they compare
   the answer with the expected answer and don't read the context. So that they can't see it,
   a judge doesn't open the question files; it prints the fields it needs with a Python one-liner
   (`id`, `type`, `question`, `expected`, `answer` of each question in its batch) and writes
   `<id>.judge<n>.json` with the Write tool.
3. `report` and `carry` work as for retrieval; `carry` compares the answers.
4. A miss is traced with the retrieval verdict on the same context (the retrieval runs in
   "Final runs"): if the context held the item, the answer step lost it.

## Calibration

Before the first run, two judges each scored the same eight contexts built from the graph, with
verdicts known in advance (complete, partial, missing, an incomplete set, a planted conflict,
noise around the answer). The result is in rag_design.md, under "How we judge retrieval".
