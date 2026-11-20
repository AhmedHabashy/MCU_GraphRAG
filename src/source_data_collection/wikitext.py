"""Turning Wikipedia wikitext into plain text and structured episode entries."""

import re

import mwparserfromhell
from mwparserfromhell.nodes import Comment, Heading, Tag, Template, Wikilink

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
    """`Title`, else `RTitle` (a title shown without quotation marks, e.g. 'Episode 1'),
    else the `Title_<n>` segments of one episode joined with ' / '."""
    return _param(template, "Title") or _param(template, "RTitle") or " / ".join(
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


def _template_source(wikitext, template_name):
    """Source text of the first `template_name` template, up to its matching '}}', or None."""
    start = re.compile(r"\{\{\s*" + re.escape(template_name) + r"\s*(?=\||\}\})", re.IGNORECASE)
    for match in start.finditer(wikitext):
        depth, i = 0, match.start()
        while i < len(wikitext):
            if wikitext.startswith("{{", i):
                depth, i = depth + 1, i + 2
            elif wikitext.startswith("}}", i):
                depth, i = depth - 1, i + 2
                if depth == 0:
                    return wikitext[match.start():i]
            else:
                i += 1
    return None


def infobox_params(wikitext, template_name):
    """Non-empty parameters of the first `template_name` template, as raw wikitext. Only the
    template's own text is parsed, and '' / ''' are left as text: an unclosed italic (often in a
    reference) can otherwise make the parser merge parameters or read the template as text."""
    source = _template_source(wikitext, template_name)
    if source is None:
        return {}
    template = mwparserfromhell.parse(source, skip_style_tags=True).filter_templates(recursive=False)[0]
    return {str(p.name).strip(): str(p.value).strip() for p in template.params if str(p.value).strip()}


_LINK_TEMPLATES = {"m"}  # Marvel Database {{m|Page|Shown text}}
_LIST_SEPARATORS = re.compile(r"\n|\*|<br\s*/?>|;|,")
_STATUS_PREFIX = re.compile(r"^(formerly|currently|former|current)\s*:?\s*", re.IGNORECASE)


def name_list(value):
    """Split an infobox list (bullets, line breaks, ';' or ',') into plain names. References,
    notes (<small>(birth name)</small>) and comments go first: they are not part of a name, and
    a comma inside them is not a separator."""
    code = mwparserfromhell.parse(value)
    for node in [*code.filter_comments(recursive=False),
                 *(t for t in code.filter_tags(recursive=False)
                   if str(t.tag).lower() in _DROPPED_TAGS | _NOTE_TAGS)]:
        code.remove(node)
    for template in code.filter_templates(recursive=False):
        name = str(template.name).strip().lower()
        if name in _LINK_TEMPLATES and template.params:
            shown = template.params[1] if len(template.params) > 1 else template.params[0]
            code.replace(template, str(shown.value))
        else:
            code.remove(template)
    names = []
    for piece in _LIST_SEPARATORS.split(str(code)):
        name = _STATUS_PREFIX.sub("", plain_text(piece)).strip()
        if name:
            names.append(name)
    return names


_NOTE_TAGS = {"ref", "small", "sup"}
_FORMERLY = re.compile(r"\bformerly\b", re.IGNORECASE)


def member_links(value):
    """Linked members of an infobox list, in order: {page, name (display text), former}.
    Everything after 'Formerly:' is former; links inside italic or bold text count, links
    inside notes, references and templates are ignored."""
    members, former = [], False

    def walk(nodes):
        nonlocal former
        for node in nodes:
            if isinstance(node, Tag):
                if str(node.tag).lower() not in _NOTE_TAGS:
                    walk(node.contents.nodes)
            elif isinstance(node, Wikilink):
                page = str(node.title).strip()
                name = plain_text(str(node.text)) if node.text else page
                members.append({"page": page, "name": name, "former": former})
            elif not isinstance(node, Template) and _FORMERLY.search(str(node)):
                former = True

    walk(mwparserfromhell.parse(value).nodes)
    return members


def transcluded_pages(wikitext):
    """Pages pulled in with {{:Page name}}."""
    return [str(t.name).strip()[1:].strip()
            for t in mwparserfromhell.parse(wikitext).filter_templates()
            if str(t.name).strip().startswith(":")]
