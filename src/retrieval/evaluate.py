"""Run the 50 evaluation questions (docs/evaluation_questions.md) through the agent and grade them,
telling retrieval misses from answer misses.

The judge model (the QA model) splits each expected answer into key facts, marks each as core
(it answers what the question asks) or supporting (context, evidence, runners-up), and checks
every fact twice: is it in what the tools returned (retrieved; also when it follows from the
retrieved values or the agent's query applied it), and is it in the answer (answered). It also
lists the answer's claims that contradict the expected answer, and those the retrieved data does
not support (from the model's own knowledge, or made up). From the core facts:
  grade   CORRECT   every core fact answered, nothing contradicting it
          PARTIAL   some answered
          WRONG     none answered
  cause   a core fact not retrieved: QUERY when the graph has the answer (the graph-only
          evaluation, src.graph.evaluate, gives PASS or FACTS FOUND), so the agent's tool calls
          missed it; DATA when the graph lacks it; QUERY/DATA when the graph has part of it.
          GENERATION: a retrieved core fact left out of the answer, or contradicted.
          Several are joined by "+"; OK when there is no miss.
  complete: every fact, supporting ones too, answered, so a looser grade can't hide thin answers.
  core retrieval recall: the share of core facts retrieved.
Before the questions, the judge checks three hand-written calibration cases (one per grade, and
both causes); the run stops if it gets any wrong, since its verdicts could not be trusted.

Pass bar: at least 39 CORRECT and a title cited in every answer. The JSON report keeps each
question's full tool results, so a verdict can be checked against what was retrieved.

Output: processed_data/retrieval/eval/<UTC time>.json and .md
Run:    .venv\\Scripts\\python.exe -m src.retrieval.evaluate             (all 50)
        .venv\\Scripts\\python.exe -m src.retrieval.evaluate Q05 Q28     (only these)
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from src.graph import evaluate as graph_evaluation
from src.retrieval.agent import open_agent
from src.source_data_collection.tier_titles import PROJECT_ROOT

QUESTIONS_PATH = PROJECT_ROOT / "docs" / "evaluation_questions.md"
REPORT_DIR = PROJECT_ROOT / "processed_data" / "retrieval" / "eval"
PASS_BAR = 39
WORKERS = 4
GRADES = ("CORRECT", "PARTIAL", "WRONG")
MISSES = ("QUERY", "QUERY/DATA", "DATA", "RETRIEVAL", "GENERATION")
IN_GRAPH = {"PASS": "QUERY", "FACTS FOUND": "QUERY", "PARTIAL": "QUERY/DATA"}   # any other status: DATA
MAX_RETRIEVED_CHARS = 80_000     # of tool results shown to the judge

JUDGE_PROMPT = """You check a Marvel films and series chatbot. It answered a question using tools that
query a knowledge graph and plot summaries. Compare its answer with the expected answer and with
what its tools retrieved.

Question: {question}

Expected answer: {expected}

Retrieved by the tools:
{retrieved}

Chatbot answer: {answer}

1. Split the expected answer into its key facts (names, numbers, titles, yes/no, events), one
   short sentence each.
2. For each key fact:
   - "core" is true if it answers what the question asks; false if it is context, evidence for
     the answer (the dates behind a computed age), or extra detail the question does not ask for.
   - "retrieved" is true if the retrieved data contains it, or it follows directly from retrieved
     values (an age from two dates, a count of listed rows), or the tool call itself applied it
     (a filter or exclusion written in the query).
   - "answered" is true if the chatbot answer states it. Wording, order and rounding as in the
     expected answer don't matter.
3. "contradictions": claims of the answer that contradict the expected answer.
4. "unsupported": claims of the answer that the retrieved data does not support. Ignore the
   Sources line."""

VERDICT_SCHEMA = {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["facts", "contradictions", "unsupported"],
    "properties": {
        "facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["fact", "core", "retrieved", "answered"],
            "properties": {"fact": {"type": "string"}, "core": {"type": "boolean"},
                           "retrieved": {"type": "boolean"}, "answered": {"type": "boolean"}}}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "unsupported": {"type": "array", "items": {"type": "string"}}}}}}

CALIBRATION = [
    {"question": "In what year is Captain Marvel set?", "expected": "1995.",
     "retrieved": '[run_cypher {"query": "MATCH (t:Title {qid: \'Q23891221\'}) RETURN t.title, t.start_year"}]\n'
                  '{"rows": [{"t.title": "Captain Marvel", "t.start_year": 1995}]}',
     "answer": "Captain Marvel is set in 1995. It was directed by Anna Boden and Ryan Fleck.\n\nSources: Captain Marvel",
     "grade": "CORRECT", "cause": "OK", "unsupported": True},
    {"question": "Who has been a member of both the Avengers and the Guardians of the Galaxy?",
     "expected": "Thor, Nebula and Rocket.",
     "retrieved": '[run_cypher {"query": "MATCH (c)-[:MEMBER_OF]->(:Team {id: \'Avengers@Earth-616\'}) ..."}]\n'
                  '{"rows": [{"name": "Thor"}, {"name": "Nebula"}, {"name": "Rocket"}]}',
     "answer": "Thor and Rocket.\n\nSources: Avengers: Endgame", "grade": "PARTIAL", "cause": "GENERATION"},
    {"question": "Which title grossed the most?", "expected": "Avengers: Endgame, about $2.80 billion.",
     "retrieved": '[run_cypher {"query": "MATCH (t:Title {type: \'Film\', year: 2018}) RETURN t.title, t.box_office_usd '
                  'ORDER BY t.box_office_usd DESC LIMIT 1"}]\n'
                  '{"rows": [{"t.title": "Avengers: Infinity War", "t.box_office_usd": 2052415039}]}',
     "answer": "Avengers: Infinity War, with about $2.05 billion.\n\nSources: Avengers: Infinity War",
     "grade": "WRONG", "cause": "RETRIEVAL+GENERATION"},
    {"question": "How old was Chris Hemsworth when Thor was first released?",
     "expected": "27: born on 11 August 1983; Thor was first released on 17 April 2011.",
     "retrieved": '[run_cypher {"query": "MATCH (p:Person {name: \'Chris Hemsworth\'}) RETURN p.birth_date"}]\n'
                  '{"rows": [{"p.birth_date": "1983-08-11"}]}\n\n'
                  '[run_cypher {"query": "MATCH (t:Title {title: \'Thor\'}) RETURN t.first_release_date"}]\n'
                  '{"rows": [{"t.first_release_date": "2011-04-17"}]}',
     "answer": "Chris Hemsworth was 27.\n\nSources: Thor",
     "grade": "CORRECT", "cause": "OK", "supporting_left_out": True},
]
CALIBRATION_GRAPH_STATUS = None    # the cases are invented, so a retrieval miss is plain "RETRIEVAL"


def parse_questions(markdown):
    """The rows of the first table: {id, type, question, expected, source}."""
    questions = []
    for line in markdown.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) == 5 and re.fullmatch(r"Q\d+", cells[0]):
            questions.append(dict(zip(("id", "type", "question", "expected", "source"), cells)))
        elif questions and not line.strip():
            break
    return questions


def retrieved_text(steps, max_chars=MAX_RETRIEVED_CHARS):
    """The tool calls and their results as the judge reads them, cut to max_chars."""
    if not steps:
        return "(no tool was called)"
    text = "\n\n".join(f"[{s['tool']} {json.dumps(s['arguments'], ensure_ascii=False)}]\n{s['result']}" for s in steps)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (cut)"


def diagnose(verdict, graph_status):
    """Grade, cause, completeness and retrieval recall from the judge's fact checks."""
    facts = verdict["facts"]
    core = [f for f in facts if f["core"]] or facts
    not_retrieved = [f["fact"] for f in core if not f["retrieved"]]
    dropped = [f["fact"] for f in core if f["retrieved"] and not f["answered"]]
    answered = [f for f in core if f["answered"]]
    contradictions = verdict["contradictions"]
    if len(answered) == len(core) and not contradictions:
        grade_ = "CORRECT"
    else:
        grade_ = "PARTIAL" if answered else "WRONG"
    retrieval = "RETRIEVAL" if graph_status is None else IN_GRAPH.get(graph_status, "DATA")
    causes = [name for name, found in ((retrieval, not_retrieved), ("GENERATION", dropped or contradictions)) if found]
    return {"grade": grade_, "cause": "+".join(causes) or "OK",
            "complete": all(f["answered"] for f in facts) and not contradictions,
            "retrieval_recall": round((len(core) - len(not_retrieved)) / len(core), 2),
            "not_retrieved": not_retrieved, "dropped": dropped, "contradictions": contradictions,
            "supporting_left_out": [f["fact"] for f in facts if f not in core and not f["answered"]],
            "unsupported": verdict["unsupported"], "graph_status": graph_status, "facts": facts}


def judge(model, question, expected, retrieved, answer, graph_status):
    """The diagnosis of one answer, with the judge's cost."""
    response = model.chat([{"role": "user", "content": JUDGE_PROMPT.format(
        question=question, expected=expected, retrieved=retrieved, answer=answer)}], response_format=VERDICT_SCHEMA)
    verdict = json.loads(response["choices"][0]["message"]["content"])
    if not verdict.get("facts"):
        raise ValueError("the judge split the expected answer into no facts")
    return {**diagnose(verdict, graph_status), "cost": (response.get("usage") or {}).get("cost", 0)}


def calibration_failures(model):
    """The calibration cases the judge gets wrong (empty when it is trustworthy)."""
    failures = []
    for case in CALIBRATION:
        v = judge(model, case["question"], case["expected"], case["retrieved"], case["answer"],
                  CALIBRATION_GRAPH_STATUS)
        checks = [(v["grade"], v["cause"]) == (case["grade"], case["cause"]),
                  not case.get("unsupported") or v["unsupported"],
                  not case.get("supporting_left_out") or v["supporting_left_out"]]
        if not all(checks):
            failures.append(f"{case['question']!r}: expected {case['grade']}/{case['cause']}, judged "
                            f"{v['grade']}/{v['cause']} (unsupported: {v['unsupported']}; "
                            f"supporting left out: {v['supporting_left_out']})")
    return failures


def _plain(text):
    return re.sub(r"[*_`]", "", text).casefold()


def cites_a_title(answer, titles):
    answer = _plain(answer)
    return any(_plain(t) in answer for t in titles)


def summary(results):
    n = len(results)
    return {"questions": n, **{g: sum(r["grade"] == g for r in results) for g in GRADES},
            "complete answers": sum(r["complete"] for r in results),
            "no miss": sum(r["cause"] == "OK" for r in results),
            **{f"misses {m}": sum(m in r["cause"].split("+") for r in results) for m in MISSES},
            "core retrieval recall": round(sum(r["retrieval_recall"] for r in results) / n, 2) if n else 0,
            "answers with unsupported claims": sum(bool(r["unsupported"]) for r in results),
            "cite a title": sum(r["cites"] for r in results),
            "cost": round(sum(r["cost"] for r in results), 6),
            "average rounds": round(sum(r["rounds"] for r in results) / n, 2) if n else 0}


def run_question(agent, titles, graph_status, q):
    result = agent.answer([{"role": "user", "content": q["question"]}])
    verdict = judge(agent.model, q["question"], q["expected"], retrieved_text(result["steps"]), result["answer"],
                    graph_status)
    return {**q, "answer": result["answer"], **{k: v for k, v in verdict.items() if k != "cost"},
            "cites": cites_a_title(result["answer"], titles), "rounds": result["rounds"],
            "tools": [s["tool"] for s in result["steps"]], "steps": result["steps"], "usage": result["usage"],
            "cost": round(result["usage"]["cost"] + verdict["cost"], 8)}


def _cell(items):
    return "; ".join(items).replace("|", "/")


def markdown_report(results, totals, model):
    met = totals["CORRECT"] >= PASS_BAR and totals["cite a title"] == totals["questions"]
    lines = [f"# Retrieval evaluation ({model})", "", " | ".join(f"{k}: {v}" for k, v in totals.items()),
             f"Pass bar: {PASS_BAR} CORRECT and a title cited in every answer: {'MET' if met else 'NOT MET'}", "",
             "| ID | Grade | Cause | Graph | Recall | Core not retrieved | Core retrieved but left out / contradicted "
             "| Supporting left out | Unsupported | Tools |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['id']} | {r['grade']}{'' if r['cites'] else ' (no title cited)'} | {r['cause']} | "
                     f"{r['graph_status']} | {r['retrieval_recall']} | {_cell(r['not_retrieved'])} | "
                     f"{_cell(r['dropped'] + [f'contradicts: {c}' for c in r['contradictions']])} | "
                     f"{_cell(r['supporting_left_out'])} | {_cell(r['unsupported'])} | {', '.join(r['tools'])} |")
    lines += ["", "## Answers", ""]
    for r in results:
        lines += [f"### {r['id']} {r['grade']} ({r['cause']}): {r['question']}", "", f"Expected: {r['expected']}", "",
                  r["answer"], ""]
    return "\n".join(lines)


def main():
    only = set(sys.argv[1:])
    questions = [q for q in parse_questions(QUESTIONS_PATH.read_text(encoding="utf-8")) if not only or q["id"] in only]
    with open_agent() as agent:
        failures = calibration_failures(agent.model)
        if failures:
            sys.exit("The judge failed calibration; no questions were run:\n  " + "\n  ".join(failures))
        titles = [r["title"] for r in agent.tools.run_cypher("MATCH (t:Title) RETURN t.title AS title")["rows"]]
        in_graph = {qid: status for qid, (_, status, _) in graph_evaluation.statuses(
            lambda cypher, **params: agent.tools.driver.execute_query(cypher, **params).records).items()}
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(lambda q: run_question(agent, titles, in_graph.get(q["id"]), q), questions))
    totals = summary(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{stamp}.json").write_text(json.dumps({"model": agent.model.chat_model, "totals": totals,
                                                          "results": results}, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    (REPORT_DIR / f"{stamp}.md").write_text(markdown_report(results, totals, agent.model.chat_model), encoding="utf-8")
    for r in results:
        print(f"{r['id']} {r['grade']:8} {r['cause']:22} graph {str(r['graph_status']):12} "
              f"recall {r['retrieval_recall']:<4} {_cell(r['not_retrieved'] + r['dropped'])[:100]}")
    print(totals)
    print(f"Report: {REPORT_DIR / stamp}.md")


if __name__ == "__main__":
    main()
