"""Collect each title's Wikipedia production section (development, writing, casting, filming).

It is the plan's source for which comic storylines a title adapts or draws on (to be extracted
later; comics themselves are out of scope for now), and for behind-the-scenes questions.

Needs:  build_title_registry
Output: source_data/wikipedia/production/<title QID>.json  (section wikitext and plain text)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_production
"""

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.storage import read_csv, utc_now, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.source_data_collection.wikitext import plain_text
from src.utils import WikimediaClient, enwiki_url

PRODUCTION_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "production"
PRODUCTION_HEADINGS = ("Production", "Development")  # some articles start with "Development"


def production_path(title_qid):
    return PRODUCTION_DIR / f"{title_qid}.json"


def production_record(title, client, retrieved_at):
    section = client.top_level_section(title["enwiki_title"], prefix=PRODUCTION_HEADINGS)
    return {"title": title["title"], "title_qid": title["wikidata_qid"],
            "page": section["page"] if section else title["enwiki_title"],
            "revid": section["revid"] if section else "",
            "heading": section["heading"] if section else "",
            "wikitext": section["wikitext"] if section else "",
            "text": plain_text(section["wikitext"]) if section else "",
            "source": "wikipedia", "source_url": enwiki_url(section["page"] if section else title["enwiki_title"]),
            "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE}


def main():
    retrieved_at = utc_now()
    client = WikimediaClient()
    titles = read_csv(REGISTRY_PATH)
    found = 0
    for title in titles:
        record = production_record(title, client, retrieved_at)
        write_json(production_path(title["wikidata_qid"]), record)
        found += bool(record["text"])
    print(f"Production sections for {found}/{len(titles)} titles")


if __name__ == "__main__":
    main()
