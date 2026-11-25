"""Prepare plot text for the fact-extraction agents (see src/graph/extraction_prompt.md).

Each film is one chunk; a series is split into chunks of whole episodes of at most MAX_CHARS.
Each chunk gets the title's cast (from the built character tables) and the team IDs. A chunk
input is rewritten only when its content changed, so a chunk is pending only when its output
is missing or older than its input: rerunning extracts only what is new or changed.

Needs:  source_data/wikipedia/plots/, processed_data/characters/, processed_data/teams/
Output: processed_data/extraction/plots/inputs/<chunk>.json   (one per chunk)
        processed_data/extraction/plots/batches.json          (pending chunks, grouped per agent)
Run:    .venv\\Scripts\\python.exe -m src.graph.prepare_extraction
"""

import json

from src.processing.build_characters import ALIASES_PATH, CHARACTERS_PATH, PERFORMANCES_PATH
from src.processing.build_teams import TEAMS_PATH
from src.source_data_collection.storage import read_csv, read_json, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

PLOTS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "plots"
EXTRACTION_DIR = PROJECT_ROOT / "processed_data" / "extraction" / "plots"
INPUTS_DIR = EXTRACTION_DIR / "inputs"
OUTPUTS_DIR = EXTRACTION_DIR / "outputs"
BATCHES_PATH = EXTRACTION_DIR / "batches.json"
MAX_CHARS = 25_000        # text per chunk
BATCH_CHARS = 40_000      # text per agent
MAX_ALIASES = 12          # per cast entry, to keep inputs small


def episode_text(episode):
    return (f"Episode {episode['number_overall']} (season {episode['season']}, episode "
            f"{episode['number_in_season']}): {episode['title']}\n{episode['summary_text']}")


def text_chunks(plot, max_chars=MAX_CHARS):
    """The plot as one chunk (films), or whole episodes grouped up to max_chars (series)."""
    episodes = [episode_text(e) for e in plot.get("episodes") or [] if e.get("summary_text")]
    if not episodes:
        return [plot["text"]] if plot.get("text") else []
    chunks, current = [], []
    for text in episodes:
        if current and len("\n\n".join(current + [text])) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
        current.append(text)
    return chunks + ["\n\n".join(current)]


def title_cast(title_qid, performances, characters, aliases):
    """The characters performed in a title, with what the agent needs to recognize them."""
    cast = {}
    for p in performances:
        cid = p["character_id"]
        if p["title_qid"] == title_qid and cid and cid not in cast:
            c = characters[cid]
            cast[cid] = {"id": cid, "label": c["label"], "reality": c["reality"], "actor": p["actor_name"],
                         "aliases": sorted(aliases.get(cid, set()) - {c["label"]})[:MAX_ALIASES]}
    return list(cast.values())


def chunk_inputs(plot, cast, teams):
    """{chunk ID: input} for one title."""
    chunks = text_chunks(plot)
    return {(plot["title_qid"] if len(chunks) == 1 else f"{plot['title_qid']}_part{i}"):
            {"title": plot["title"], "title_qid": plot["title_qid"], "cast": cast, "teams": teams, "text": text}
            for i, text in enumerate(chunks, 1)}


def pending(chunk_ids, inputs_dir=INPUTS_DIR, outputs_dir=OUTPUTS_DIR):
    """Chunks with no output, or an output older than their input."""
    def stale(cid):
        out = outputs_dir / f"{cid}.json"
        return not out.exists() or out.stat().st_mtime < (inputs_dir / f"{cid}.json").stat().st_mtime
    return [c for c in chunk_ids if stale(c)]


def batches(chunks, batch_chars=BATCH_CHARS):
    """Pending chunk IDs grouped so that each agent gets about batch_chars of text."""
    groups, current, size = [], [], 0
    for cid, length in chunks:
        if current and size + length > batch_chars:
            groups.append(current)
            current, size = [], 0
        current.append(cid)
        size += length
    return groups + ([current] if current else [])


def write_if_changed(path, value):
    if not path.exists() or read_json(path) != value:
        write_json(path, value)


def main():
    characters = {r["character_id"]: r for r in read_csv(CHARACTERS_PATH)}
    aliases = {}
    for a in read_csv(ALIASES_PATH):
        aliases.setdefault(a["character_id"], set()).add(a["alias"])
    performances = read_csv(PERFORMANCES_PATH)
    teams = [t["team_id"] for t in read_csv(TEAMS_PATH)]

    inputs = {}
    for path in sorted(PLOTS_DIR.glob("*.json")):
        plot = read_json(path)
        inputs |= chunk_inputs(plot, title_cast(plot["title_qid"], performances, characters, aliases), teams)
    for cid, value in inputs.items():
        write_if_changed(INPUTS_DIR / f"{cid}.json", value)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    todo = pending(list(inputs))
    groups = batches([(c, len(inputs[c]["text"])) for c in todo])
    BATCHES_PATH.write_text(json.dumps(groups, indent=1), encoding="utf-8")
    print(f"{len(inputs)} chunks, {len(todo)} pending, in {len(groups)} agent batches")


if __name__ == "__main__":
    main()
