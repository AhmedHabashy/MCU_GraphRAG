"""Turning Wikipedia wikitext into plain text and structured episode entries."""

import re

import mwparserfromhell
from mwparserfromhell.nodes import Comment, Heading, Tag, Template

_DATE_TEMPLATES = {"start date", "start date and age", "dts"}
_DROPPED_TAGS = {"ref", "references"}


def plain_text(wikitext):
    """Readable text: link labels kept; templates, refs, comments and headings removed."""
    code = mwparserfromhell.parse(wikitext)
    for node in list(code.nodes):
        if isinstance(node, (Template, Comment, Heading)) or (
                isinstance(node, Tag) and str(node.tag).lower() in _DROPPED_TAGS):
            code.remove(node)
    text = code.strip_code(normalize=True, collapse=True)
    paragraphs = (" ".join(p.split()) for p in re.split(r"\n\s*\n", text))
    return "\n\n".join(p for p in paragraphs if p)


def _param(template, name):
    return str(template.get(name).value).strip() if template.has(name) else ""


def _number(text):
    return int(text) if text.isdigit() else None


def _air_date(value):
    for template in mwparserfromhell.parse(value).filter_templates():
        if str(template.name).strip().lower() in _DATE_TEMPLATES:
            parts = [str(p.value).strip() for p in template.params if not p.showkey][:3]
            if parts and all(p.isdigit() for p in parts):
                return "-".join([parts[0].zfill(4)] + [p.zfill(2) for p in parts[1:]])
    return ""


def _part_param(template, name, part):
    """`name_<part>` if the template has it, else the shared `name`."""
    return _param(template, f"{name}_{part}") or _param(template, name)


def _num_parts(template):
    return _number(_param(template, "NumParts")) or 1


def _title(template, parts):
    """`Title`, or the `Title_<n>` segments of one episode joined with ' / '."""
    return _param(template, "Title") or " / ".join(
        t for t in (_param(template, f"Title_{i}") for i in range(1, parts + 1)) if t)


def episode_entries(wikitext):
    """One dict per episode in {{Episode list}} / {{Episode list/sublist}} templates.

    A template with NumParts and numbered EpisodeNumber_<n> params holds several
    episodes that share a title and summary; each becomes its own entry, marked with
    `part` / `num_parts`. NumParts with a single EpisodeNumber is one episode whose
    title has several segments (Title_<n>).
    """
    episodes = []
    for template in mwparserfromhell.parse(wikitext).filter_templates():
        if not str(template.name).strip().lower().startswith("episode list"):
            continue
        parts = _num_parts(template) if template.has("EpisodeNumber_1") else 1
        summary = _param(template, "ShortSummary")
        title = plain_text(_title(template, _num_parts(template)))
        for part in range(1, parts + 1):
            overall = _number(_part_param(template, "EpisodeNumber", part))
            in_season = _number(_part_param(template, "EpisodeNumber2", part))
            episodes.append({
                "number_overall": overall,
                "number_in_season": in_season if in_season is not None else overall,
                "title": title,
                "air_date": _air_date(_part_param(template, "OriginalAirDate", part)),
                "part": part,
                "num_parts": parts,
                "summary_wikitext": summary,
                "summary_text": plain_text(summary),
            })
    return episodes


def transcluded_pages(wikitext):
    """Pages pulled in with {{:Page name}}."""
    return [str(t.name).strip()[1:].strip()
            for t in mwparserfromhell.parse(wikitext).filter_templates()
            if str(t.name).strip().startswith(":")]
