"""Automatic checks on a written summary against its input (docs/rag_design.md, "Summaries").

Problems (the writer must fix them):
  - a missing field, or kind / id / name / input_hash differing from the input
  - a summary outside MIN_WORDS..MAX_WORDS words
  - fewer than 3 or more than 10 key facts; a key fact without a fact, or whose cite isn't
    citations like [Q1] or [Q1 ep 2], or cites one the input doesn't have
Warnings (for review, not failures):
  - capitalized names in the summary that the input never mentions (a heuristic)

Run:  .venv\\Scripts\\python.exe -m src.graph.check_summaries <input.json> <output.json>
      .venv\\Scripts\\python.exe -m src.graph.check_summaries              (every output)
"""

import re
import sys

from src.graph.summary_inputs import INPUTS_DIR, OUTPUTS_DIR, citations
from src.source_data_collection.storage import read_json

FIELDS = ("kind", "id", "name", "input_hash", "summary", "key_facts", "writer")
COPIED = ("kind", "id", "name", "input_hash")
MIN_WORDS, MAX_WORDS = 60, 250
MIN_KEY_FACTS, MAX_KEY_FACTS = 3, 10
CITE = re.compile(r"\[Q\d+(?: ep \d+)?\](?: \[Q\d+(?: ep \d+)?\])*")
NAME_WORD = re.compile(r"[A-Z][\w'’.\-]*")
EDGE_PUNCTUATION = "\"“”()[],;:!?."


def unknown_names(summary, input_text):
    """Runs of capitalized words the input never mentions. A sentence's first word is skipped,
    since it is capitalized anyway."""
    known, found = input_text.casefold(), []
    for sentence in re.split(r"(?<=[.!?])\s+", summary):
        run = []
        for position, token in enumerate(sentence.split()):
            word = token.strip(EDGE_PUNCTUATION).removesuffix("'s").removesuffix("’s")
            if NAME_WORD.fullmatch(word) and position > 0:
                run.append(word)
            elif run:
                found.append(" ".join(run))
                run = []
            if run and token[-1] in EDGE_PUNCTUATION:      # a comma or a full stop ends a name
                found.append(" ".join(run))
                run = []
        if run:
            found.append(" ".join(run))
    return list(dict.fromkeys(n for n in found if n.casefold() not in known))


def check(inp, out):
    """(problems, warnings) of one output against its input."""
    missing = [f for f in FIELDS if f not in out]
    if missing:
        return [f"missing {', '.join(missing)}"], []
    problems = [f"{f} is {out[f]!r}, the input has {inp[f]!r}" for f in COPIED if out[f] != inp[f]]
    words = len(out["summary"].split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"summary has {words} words ({MIN_WORDS} to {MAX_WORDS})")
    facts = out["key_facts"]
    if not MIN_KEY_FACTS <= len(facts) <= MAX_KEY_FACTS:
        problems.append(f"{len(facts)} key facts ({MIN_KEY_FACTS} to {MAX_KEY_FACTS})")
    in_input = citations(inp["text"])
    for n, fact in enumerate(facts, 1):
        if not str(fact.get("fact", "")).strip():
            problems.append(f"key fact {n} has no fact")
        cite = str(fact.get("cite", ""))
        if not CITE.fullmatch(cite):
            problems.append(f"key fact {n}: cite {cite!r} is not citations like [Q1] or [Q1 ep 2]")
            continue
        for qid, ep in sorted(citations(cite) - in_input, key=str):
            problems.append(f"key fact {n}: [{qid}{f' ep {ep}' if ep else ''}] is not cited in the input")
    names = unknown_names(out["summary"], inp["text"])
    return problems, ([f"names not in the input: {', '.join(names)}"] if names else [])


def main():
    if len(sys.argv) == 3:
        pairs = [(read_json(sys.argv[1]), read_json(sys.argv[2]))]
    else:
        pairs = [(read_json(INPUTS_DIR / p.relative_to(OUTPUTS_DIR)), read_json(p)) for p in sorted(OUTPUTS_DIR.glob("*/*.json"))]
    with_problems = 0
    for inp, out in pairs:
        problems, warnings = check(inp, out)
        with_problems += bool(problems)
        for line in [f"PROBLEM {p}" for p in problems] + [f"WARNING {w}" for w in warnings]:
            print(f"{inp['kind']} {inp['id']}: {line}")
    print(f"{len(pairs)} summaries, {with_problems} with problems")


if __name__ == "__main__":
    main()
