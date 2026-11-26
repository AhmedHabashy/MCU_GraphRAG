"""Where every summary stands, and the batches for each next action (docs/summary_agents.md).

States, in the order they are tested:
  write    no output, or the output was written from another input (input_hash)
  fix      the automatic check (check_summaries) reports a problem
  check1   no valid check 1 newer than the output
  rewrite  a review (reviews/<kind>/<id>.json, newer than the output) fails it, or the newest check
           failed; and the summary has been rewritten fewer than MAX_REWRITES times
  flagged  the newest check failed after MAX_REWRITES rewrites: left for the user
  check2   check 1 passed, and no valid check 2 newer than the output
  kept     checks 1 and 2 both passed, both newer than the output
A check counts only if it is newer than the summary it checked, so a rewrite's old checks no
longer count. Only kept summaries are used to build the inputs of the next level.

Output: processed_data/summaries/status.json (counts, and the batches per action)
Run:    .venv\\Scripts\\python.exe -m src.graph.summary_status
"""

from src.graph.check_summaries import check
from src.graph.summary_inputs import INPUTS_DIR, OUTPUTS_DIR, SUMMARIES_DIR, batches
from src.source_data_collection.storage import read_json, write_json

CHECKS_DIR = SUMMARIES_DIR / "checks"
REVIEWS_DIR = SUMMARIES_DIR / "reviews"      # a review by the user or the main session, same shape as a check
STATUS_PATH = SUMMARIES_DIR / "status.json"
MAX_REWRITES = 2
STATES = ("write", "fix", "check1", "check2", "rewrite", "flagged", "kept")
VERDICTS = {"pass", "fail"}


def fresh_check(check_path, output_path, whole=True):
    """The check's result if it exists, is newer than the output, has a valid verdict and (for a
    whole check) lists at least as many statements as the summary has key facts: each key fact is
    a statement of its own, so a check that lumps them together doesn't count. A review need only
    name what is wrong (whole=False). Else None."""
    if not check_path.exists() or check_path.stat().st_mtime <= output_path.stat().st_mtime:
        return None
    result = read_json(check_path)
    if result.get("verdict") not in VERDICTS:
        return None
    if whole and len(result.get("statements", [])) < len(read_json(output_path).get("key_facts", [])):
        return None
    return result


def state(inp, out, problems, check1, check2, review=None):
    """(state, the failing check's name or None) of one summary; check1, check2 and review are
    fresh. A review that fails the summary sends it back even when both checks passed."""
    if out is None or out.get("input_hash") != inp["input_hash"]:
        return "write", None
    if problems:
        return "fix", None
    if review is not None and review["verdict"] == "fail":
        return ("rewrite" if out.get("rewrites", 0) < MAX_REWRITES else "flagged"), "review"
    for name, result in (("check1", check1), ("check2", check2)):
        if result is None:
            return name, None
        if result["verdict"] == "fail":
            return ("rewrite" if out.get("rewrites", 0) < MAX_REWRITES else "flagged"), name
    return "kept", None


def check_path(kind, file, n):
    return CHECKS_DIR / kind / file.replace(".json", f".check{n}.json")


def review_path(kind, file):
    return REVIEWS_DIR / kind / file


def failing_path(kind, file, failing):
    """The file of the check (check1, check2) or review that failed a summary."""
    return review_path(kind, file) if failing == "review" else check_path(kind, file, failing[-1])


def summary_states():
    """[(file name, input, output or None, state, failing check)] for every current input."""
    rows = []
    for input_path in sorted(INPUTS_DIR.glob("*/*.json")):
        inp, kind, file = read_json(input_path), input_path.parent.name, input_path.name
        output_path = OUTPUTS_DIR / kind / file
        out = read_json(output_path) if output_path.exists() else None
        problems = check(inp, out)[0] if out else []
        checks = [fresh_check(check_path(kind, file, n), output_path) if out else None for n in (1, 2)]
        review = fresh_check(review_path(kind, file), output_path, whole=False) if out else None
        rows.append((file, inp, out, *state(inp, out, problems, *checks, review=review)))
    return rows


def kept_outputs():
    """{(kind, id): output} of the kept summaries: what the next level's inputs may be built from."""
    return {(inp["kind"], inp["id"]): out for _, inp, out, st, _ in summary_states() if st == "kept"}


def work_item(file, inp, out, failing):
    """What an agent is given for one summary: kind and file, and for a rewrite the failing check
    and the new rewrite count."""
    item = {"kind": inp["kind"], "file": file}
    if failing:
        item.update(check=str(failing_path(inp["kind"], file, failing).relative_to(SUMMARIES_DIR)),
                    rewrites=out.get("rewrites", 0) + 1)
    return item


def main():
    rows = summary_states()
    by_state, by_kind = {}, {}
    for file, inp, out, st, failing in rows:
        by_state.setdefault(st, []).append((work_item(file, inp, out, failing), inp))
        by_kind.setdefault(inp["kind"], {}).setdefault(st, 0)
        by_kind[inp["kind"]][st] += 1
    counts = {s: len(by_state.get(s, [])) for s in STATES}
    actions = {}
    for s in ("write", "fix", "check1", "check2", "rewrite"):
        if s in by_state:
            items = {(inp["kind"], inp["id"]): item for item, inp in by_state[s]}
            actions[s] = [[items[(i["kind"], i["id"])] for i in group] for group in batches([i for _, i in by_state[s]])]
    write_json(STATUS_PATH, {"counts": counts, "by_kind": by_kind, "actions": actions,
                             "flagged": [item for item, _ in by_state.get("flagged", [])]})
    print(" | ".join(f"{s} {n}" for s, n in counts.items()))
    for kind, states in by_kind.items():
        print(f"  {kind:10} " + ", ".join(f"{s} {n}" for s, n in states.items()))
    for s, groups in actions.items():
        print(f"{s}: {len(groups)} batches")


if __name__ == "__main__":
    main()
