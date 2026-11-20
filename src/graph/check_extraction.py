"""Checks on an extraction agent's output (see src/graph/extraction_prompt.md).

Run:  .venv\Scripts\python.exe -m src.graph.check_extraction <input.json> <output.json>
"""

import json
import sys
from pathlib import Path

RELATIONS = {"ALLY_OF", "ENEMY_OF", "KILLS", "RESCUES", "FAMILY_OF", "ROMANCE_WITH", "MEMBER_OF",
             "WORKS_FOR", "LEADS", "VARIANT_OF", "IMPERSONATES", "POSSESSES", "TRAVELS_TO", "CREATES"}
OBJECT_TYPES = {"character", "team", "organization", "place", "object", "event", "time", "universe"}
FIELDS = ("subject_id", "subject_name", "relation", "object_id", "object_name", "object_type",
          "episode", "evidence", "note")


def fact_problems(source, output):
    """(fact index, problem) for every fact that breaks a rule; index -1 for the whole output."""
    if output.get("title_qid") != source["title_qid"]:
        return [(-1, "title_qid does not match the input")]
    known = {c["id"] for c in source["cast"]} | set(source["teams"])
    problems, seen = [], set()
    for i, fact in enumerate(output.get("facts", [])):
        missing = [f for f in FIELDS if f not in fact]
        if missing:
            problems.append((i, f"missing fields {missing}"))
            continue
        if fact["relation"] not in RELATIONS:
            problems.append((i, f"unknown relation {fact['relation']}"))
        if fact["object_type"] not in OBJECT_TYPES:
            problems.append((i, f"unknown object type {fact['object_type']}"))
        for side in ("subject_id", "object_id"):
            if fact[side] and fact[side] not in known:
                problems.append((i, f"{side} {fact[side]} is not in the cast or teams"))
        if not fact["evidence"] or fact["evidence"] not in source["text"]:
            problems.append((i, "evidence is not an exact quote of the text"))
        key = (fact["subject_id"] or fact["subject_name"], fact["relation"],
               fact["object_id"] or fact["object_name"], fact["episode"])
        if key in seen:
            problems.append((i, "duplicate fact"))
        seen.add(key)
    return problems


def main(input_path, output_path):
    source = json.loads(Path(input_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    facts = output.get("facts", [])
    problems = fact_problems(source, output)
    for i, problem in problems:
        print(f"fact {i}: {problem}")
    linked = sum(bool(f.get("subject_id")) + bool(f.get("object_id")) for f in facts)
    print(f"{len(facts)} facts, {len({i for i, _ in problems})} with problems, {linked} linked entity slots")


if __name__ == "__main__":
    main(*sys.argv[1:3])
