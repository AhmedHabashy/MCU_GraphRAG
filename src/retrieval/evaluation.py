"""Judging retrieval on the 50 evaluation questions (docs/rag_design.md, "How we judge retrieval").

Python only runs a strategy and times it; whether the retrieved context holds the expected
answer is judged by Claude Code subagents (src/retrieval/judge_prompt.md, docs/retrieval_agents.md),
since matching strings can't tell a fact from a mention.

  run     run a strategy on every question: one file per question with the context and timings,
          and the judges' batches (batches.json)
  report  the judges' verdicts and the timings of a run, as report.md

A strategy is a function (question text, question vector) -> context text. The question vectors
are embedded first, through the cache (src.retrieval.embeddings), and timed apart: the strategy's
time is the retrieval alone.

Output: processed_data/retrieval/eval/<strategy>/<run>/  (Q01.json ..., batches.json, report.md;
        the judges write Q01.judge.json ...)
Run:    .venv\\Scripts\\python.exe -m src.retrieval.evaluation run <strategy>
        .venv\\Scripts\\python.exe -m src.retrieval.evaluation report <run folder>
"""

import argparse
import statistics
import time
from datetime import datetime, timezone

from src.graph.prepare_extraction import batches
from src.source_data_collection.storage import read_json, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

QUESTIONS_PATH = PROJECT_ROOT / "docs" / "evaluation_questions.md"
EVAL_DIR = PROJECT_ROOT / "processed_data" / "retrieval" / "eval"
FIELDS = ("id", "type", "question", "expected", "source")
JUDGE_BATCH_CHARS = 60_000      # context per judge agent, as for the summary agents
VERDICTS = ("complete", "partial", "missing")
STRATEGIES = {}                 # name -> function(question, vector) -> context; filled by the strategy modules


def read_questions(path=QUESTIONS_PATH):
    """[{id, type, question, expected, source}] from the questions table."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == len(FIELDS) and cells[0][:1] == "Q" and cells[0][1:].isdigit():
            rows.append(dict(zip(FIELDS, cells)))
    return rows


def save_run(run_dir, strategy, results):
    """One file per question ({question fields, strategy, context, seconds}) and the judges'
    batches, sized by context."""
    for r in results:
        write_json(run_dir / f"{r['id']}.json", dict(r, strategy=strategy))
    write_json(run_dir / "batches.json",
               batches([(r["id"], len(r["context"]) + len(r["expected"])) for r in results], JUDGE_BATCH_CHARS))


def run(strategy, retrieve, questions, vectors, run_dir):
    """Run a strategy on every question (vectors in question order) and save the run."""
    results = []
    for q, vector in zip(questions, vectors):
        start = time.perf_counter()
        context = retrieve(q["question"], vector)
        results.append(dict(q, context=context, seconds=round(time.perf_counter() - start, 4)))
    save_run(run_dir, strategy, results)
    return results


def judged(run_dir):
    """[(question file, its judgement or None)] for the run's questions (those in its batches)."""
    rows = []
    for qid in (q for batch in read_json(run_dir / "batches.json") for q in batch):
        judge = run_dir / f"{qid}.judge.json"
        rows.append((read_json(run_dir / f"{qid}.json"), read_json(judge) if judge.exists() else None))
    return rows


def _seconds(values):
    return f"median {statistics.median(values):.3f} s, max {max(values):.3f} s" if values else "none"


def report(run_dir):
    """The report of a run as Markdown: verdicts per type and per question, the missing items,
    and the timings."""
    rows = judged(run_dir)
    strategy = rows[0][0]["strategy"] if rows else "?"
    lines = [f"# Retrieval: {strategy} ({run_dir.name})", ""]
    unjudged = [q["id"] for q, j in rows if j is None or j.get("verdict") not in VERDICTS]
    if unjudged:
        lines += [f"**Not judged yet:** {', '.join(unjudged)}", ""]
    counts = {v: sum(1 for _, j in rows if j and j.get("verdict") == v) for v in VERDICTS}
    lines += [" | ".join(f"{v} {n}" for v, n in counts.items()) + f" | of {len(rows)}", "",
              f"Retrieval time per question: {_seconds([q['seconds'] for q, _ in rows])}", "",
              "| Type | " + " | ".join(VERDICTS) + " |", "| --- |" + " --- |" * len(VERDICTS)]
    for kind in dict.fromkeys(q["type"] for q, _ in rows):
        of_kind = [j for q, j in rows if q["type"] == kind]
        lines.append(f"| {kind} | " + " | ".join(str(sum(1 for j in of_kind if j and j.get("verdict") == v))
                                                for v in VERDICTS) + " |")
    lines += ["", "| ID | Verdict | Seconds | Context chars | Missing or partly found |", "| --- | --- | --- | --- | --- |"]
    for q, j in rows:
        gaps = "; ".join(f"{i['item']} ({i['found']})" for i in (j or {}).get("items", []) if i.get("found") != "yes")
        lines.append(f"| {q['id']} | {(j or {}).get('verdict', '-')} | {q['seconds']:.3f} | {len(q['context']):,} | "
                     f"{gaps.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("run").add_argument("strategy", choices=sorted(STRATEGIES) or None)
    sub.add_parser("report").add_argument("run_dir")
    args = parser.parse_args()
    if args.action == "run":
        from src.retrieval.embeddings import vectors_for
        from src.retrieval.openrouter import from_env
        questions = read_questions()
        start = time.perf_counter()
        vectors, embedded = vectors_for("queries", [q["question"] for q in questions], from_env())
        run_dir = EVAL_DIR / args.strategy / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        results = run(args.strategy, STRATEGIES[args.strategy], questions, vectors, run_dir)
        print(f"{len(results)} questions; {embedded} question vectors embedded in "
              f"{time.perf_counter() - start:.2f} s; retrieval {_seconds([r['seconds'] for r in results])}")
        print(f"Run: {run_dir.relative_to(PROJECT_ROOT)} ({len(read_json(run_dir / 'batches.json'))} judge batches)")
    else:
        run_dir = PROJECT_ROOT / args.run_dir
        text = report(run_dir)
        (run_dir / "report.md").write_text(text, encoding="utf-8")
        print(text.split("\n\n")[1])


if __name__ == "__main__":
    main()
