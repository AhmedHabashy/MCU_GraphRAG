"""Judging retrieval and answers on the 50 evaluation questions (docs/rag_design.md, "How we
judge retrieval" and "The answer step").

Python only runs a strategy and times it; whether the retrieved context (or the answer) holds
the expected answer is judged by Claude Code subagents (src/retrieval/judge_prompt.md and
answer_judge_prompt.md, docs/retrieval_agents.md), since matching strings can't tell a fact
from a mention.

  run     run a strategy on every question: one file per question with the context and timings,
          and the judges' batches (batches.json)
  answer  the same with the answer step on top: each file also holds the answer, the views
          the model called, and the retrieval and answer times; the judges judge the answer
  carry   copy a previous run's judgements where the judged text is the same, so only changed
          questions are judged again (pending.json)
  report  the judges' verdicts and the timings of a run, as report.md

A strategy (STRATEGIES) is made from a Neo4j driver and called as (question text, question
vector) -> context text. The question vectors are embedded first, through the cache (src.retrieval.embeddings), and timed apart: the strategy's
time is the retrieval alone.

Output: processed_data/retrieval/eval/<strategy>/<run>/  (Q01.json ..., batches.json, report.md;
        judge n writes Q01.judge<n>.json ..., n = 1 .. JUDGES); answer runs under eval/answers/
Run:    .venv\\Scripts\\python.exe -m src.retrieval.evaluation run <strategy>
        .venv\\Scripts\\python.exe -m src.retrieval.evaluation answer <strategy>
        .venv\\Scripts\\python.exe -m src.retrieval.evaluation report <run folder>
"""

import argparse
import statistics
import time
from datetime import datetime, timezone

from src.graph.neo4j_db import connect
from src.graph.prepare_extraction import batches
from src.retrieval.aggregate import AggregateSearch
from src.retrieval.drift import DriftSearch
from src.retrieval.global_search import GlobalSearch
from src.retrieval.local import LocalSearch
from src.source_data_collection.storage import read_json, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

QUESTIONS_PATH = PROJECT_ROOT / "docs" / "evaluation_questions.md"
EVAL_DIR = PROJECT_ROOT / "processed_data" / "retrieval" / "eval"
FIELDS = ("id", "type", "question", "expected", "source")
JUDGE_BATCH_CHARS = 60_000      # context per judge agent, as for the summary agents
ANSWER_BATCH_CHARS = 5_000      # answers are short: about 8 questions per answer judge
VERDICTS = ("complete", "partial", "missing")      # best first
JUDGES = 2                      # independent judges per question; the lower verdict counts
STRATEGIES = {"local": LocalSearch, "global": GlobalSearch, "drift": DriftSearch, "aggregate": AggregateSearch}
ANSWERED = ("local", "global", "drift")     # the strategies the user picks from; aggregation is the model's tool


def read_questions(path=QUESTIONS_PATH):
    """[{id, type, question, expected, source}] from the questions table."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == len(FIELDS) and cells[0][:1] == "Q" and cells[0][1:].isdigit():
            rows.append(dict(zip(FIELDS, cells)))
    return rows


def judged_text(q):
    """What the judges of a question file read: the answer in an answer run, else the context."""
    return q[q.get("judged", "context")]


def _batches(questions, batch_chars):
    return batches([(q["id"], len(judged_text(q)) + len(q["expected"])) for q in questions], batch_chars)


def save_run(run_dir, strategy, results, batch_chars=JUDGE_BATCH_CHARS):
    """One file per question ({question fields, strategy, context, seconds, ...}) and the
    judges' batches, sized by the judged text."""
    for r in results:
        write_json(run_dir / f"{r['id']}.json", dict(r, strategy=strategy))
    write_json(run_dir / "batches.json", _batches(results, batch_chars))


def run(strategy, retrieve, questions, vectors, run_dir):
    """Run a strategy on every question (vectors in question order) and save the run. One
    untimed call first warms the database, so the first question isn't timed with a cold start."""
    if questions:
        retrieve(questions[0]["question"], vectors[0])
    results = []
    for q, vector in zip(questions, vectors):
        start = time.perf_counter()
        context = retrieve(q["question"], vector)
        results.append(dict(q, context=context, seconds=round(time.perf_counter() - start, 4)))
    save_run(run_dir, strategy, results)
    return results


def answer_run(strategy, answerer, questions, vectors, run_dir):
    """The answer step on every question (an Answerer: (question, vector) -> {context, answer,
    views, retrieval_seconds, answer_seconds}). The warm-up is the retrieval alone: it warms
    the database without a model call. `seconds` is the retrieval time, as in a retrieval run."""
    if questions:
        answerer.retrieve(questions[0]["question"], vectors[0])
    results = []
    for q, vector in zip(questions, vectors):
        out = answerer(q["question"], vector)
        results.append(dict(q, **out, seconds=out["retrieval_seconds"], judged="answer"))
    save_run(run_dir, strategy, results, ANSWER_BATCH_CHARS)
    return results


def judged(run_dir):
    """[(question file, [its judgement by each judge, or None])] for the run's questions (those in
    its batches)."""
    rows = []
    for qid in (q for batch in read_json(run_dir / "batches.json") for q in batch):
        paths = [run_dir / f"{qid}.judge{n}.json" for n in range(1, JUDGES + 1)]
        rows.append((read_json(run_dir / f"{qid}.json"), [read_json(p) if p.exists() else None for p in paths]))
    return rows


def combined(judgements):
    """(the verdict that counts, the judgement it comes from), or (None, None) until every judge
    has given a valid verdict. The lower verdict counts: a generous judge hides a gap."""
    if any(j is None or j.get("verdict") not in VERDICTS for j in judgements):
        return None, None
    lowest = max(judgements, key=lambda j: VERDICTS.index(j["verdict"]))
    return lowest["verdict"], lowest


def _seconds(values):
    return f"median {statistics.median(values):.3f} s, max {max(values):.3f} s" if values else "none"


def report(run_dir):
    """The report of a run as Markdown: the verdicts that count (the lower of the judges') per
    type and per question, the items not found, the questions the judges disagree on, and the
    timings."""
    rows = [(q, js, *combined(js)) for q, js in judged(run_dir)]
    strategy = rows[0][0]["strategy"] if rows else "?"
    answers = bool(rows) and rows[0][0].get("judged") == "answer"
    lines = [f"# {'Answers' if answers else 'Retrieval'}: {strategy} ({run_dir.name})", ""]
    unjudged = [q["id"] for q, _, v, _ in rows if v is None]
    if unjudged:
        lines += [f"**Not judged yet:** {', '.join(unjudged)}", ""]
    counts = {v: sum(1 for *_, verdict, _ in rows if verdict == v) for v in VERDICTS}
    lines += [" | ".join(f"{v} {n}" for v, n in counts.items()) + f" | of {len(rows)} (the lower of {JUDGES} judges)", "",
              f"Retrieval time per question: {_seconds([q['seconds'] for q, *_ in rows])}", ""]
    if answers:
        lines += [f"Answer time per question: {_seconds([q['answer_seconds'] for q, *_ in rows])}", "",
                  "Views called: " + (", ".join(f"{q['id']} ({', '.join(q['views'])})" for q, *_ in rows if q["views"])
                                      or "none"), ""]
    lines += [              "| Type | " + " | ".join(VERDICTS) + " |", "| --- |" + " --- |" * len(VERDICTS)]
    for kind in dict.fromkeys(q["type"] for q, *_ in rows):
        of_kind = [v for q, _, v, _ in rows if q["type"] == kind]
        lines.append(f"| {kind} | " + " | ".join(str(of_kind.count(v)) for v in VERDICTS) + " |")
    split = [(q["id"], [j["verdict"] for j in js]) for q, js, v, _ in rows if v and len({j["verdict"] for j in js}) > 1]
    lines += ["", f"Judges disagree on {len(split)}: " + (", ".join(f"{i} ({' / '.join(vs)})" for i, vs in split) or "none")]
    lines += ["", f"| ID | Verdict | Seconds | {'Answer' if answers else 'Context'} chars | Missing or partly found (the counting judge) |",
              "| --- | --- | --- | --- | --- |"]
    for q, _, verdict, j in rows:
        gaps = "; ".join(f"{i['item']} ({i['found']})" for i in (j or {}).get("items", []) if i.get("found") != "yes")
        lines.append(f"| {q['id']} | {verdict or '-'} | {q['seconds']:.3f} | {len(judged_text(q)):,} | {gaps.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def carry(run_dir, previous_dir):
    """Copy the previous run's judgements of every question whose judged text (the context, or
    the answer) is the same, character for character (the judges would see the same input), and
    write pending.json: the judge batches of the questions left. Returns (carried, pending)."""
    carried, left = 0, []
    for q, _ in judged(run_dir):
        before = previous_dir / f"{q['id']}.json"
        paths = [previous_dir / f"{q['id']}.judge{n}.json" for n in range(1, JUDGES + 1)]
        if before.exists() and judged_text(read_json(before)) == judged_text(q) and all(p.exists() for p in paths):
            for n, p in enumerate(paths, 1):
                write_json(run_dir / f"{q['id']}.judge{n}.json", read_json(p))
            carried += 1
        else:
            left.append(q)
    answers = any(q.get("judged") == "answer" for q in left)
    write_json(run_dir / "pending.json", _batches(left, ANSWER_BATCH_CHARS if answers else JUDGE_BATCH_CHARS))
    return carried, len(left)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    run_args = sub.add_parser("run")
    run_args.add_argument("strategy", choices=sorted(STRATEGIES))
    run_args.add_argument("--questions", help="comma-separated ids, such as Q41,Q42 (default: all)")
    answer_args = sub.add_parser("answer")
    answer_args.add_argument("strategy", choices=ANSWERED)
    answer_args.add_argument("--questions", help="comma-separated ids, such as Q41,Q42 (default: all)")
    sub.add_parser("report").add_argument("run_dir")
    carry_args = sub.add_parser("carry")
    carry_args.add_argument("run_dir")
    carry_args.add_argument("previous_dir")
    args = parser.parse_args()
    if args.action == "carry":
        carried, left = carry(PROJECT_ROOT / args.run_dir, PROJECT_ROOT / args.previous_dir)
        print(f"{carried} judgements carried over (same judged text); {left} questions to judge, in pending.json")
    elif args.action in ("run", "answer"):
        from src.retrieval.embeddings import vectors_for
        from src.retrieval.openrouter import from_env
        wanted = set(args.questions.split(",")) if args.questions else None
        every = read_questions()
        client = from_env()
        start = time.perf_counter()
        # every question is embedded, so a run on some of them doesn't drop the others from the cache
        all_vectors, embedded = vectors_for("queries", [q["question"] for q in every], client)
        chosen = [(q, v) for q, v in zip(every, all_vectors) if wanted is None or q["id"] in wanted]
        questions, vectors = [q for q, _ in chosen], [v for _, v in chosen]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        with connect() as driver:
            strategy = STRATEGIES[args.strategy](driver)
            if args.action == "run":
                run_dir = EVAL_DIR / args.strategy / stamp
                results = run(args.strategy, strategy, questions, vectors, run_dir)
            else:
                from src.retrieval.aggregate import Views
                from src.retrieval.answer import Answerer
                run_dir = EVAL_DIR / "answers" / args.strategy / stamp
                results = answer_run(args.strategy, Answerer(strategy, Views(driver), client.chat),
                                     questions, vectors, run_dir)
        print(f"{len(results)} questions; {embedded} question vectors embedded in "
              f"{time.perf_counter() - start:.2f} s; retrieval {_seconds([r['seconds'] for r in results])}")
        if args.action == "answer":
            print(f"Answers {_seconds([r['answer_seconds'] for r in results])}")
        print(f"Run: {run_dir.relative_to(PROJECT_ROOT)} ({len(read_json(run_dir / 'batches.json'))} judge batches)")
    else:
        run_dir = PROJECT_ROOT / args.run_dir
        text = report(run_dir)
        (run_dir / "report.md").write_text(text, encoding="utf-8")
        print(text.split("\n\n")[1])


if __name__ == "__main__":
    main()
