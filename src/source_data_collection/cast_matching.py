"""Comparing actor and character names across sources (TMDB, Wikidata, Wikipedia)."""

import re
import unicodedata

# Words that appear in many different characters' names, so sharing one proves nothing.
GENERIC_WORDS = {
    "a", "an", "the", "of", "and", "de", "von", "van", "la", "le", "el", "jr", "sr", "ii", "iii",
    "mr", "mrs", "ms", "dr", "sir", "lady", "lord", "miss", "mister", "doctor", "professor",
    "agent", "officer", "captain", "colonel", "major", "general", "sergeant", "commander",
    "director", "senator", "president", "king", "queen", "prince", "princess",
    "man", "woman", "boy", "girl", "kid", "young", "old", "guard", "soldier",
    "black", "red", "iron", "super", "voice", "himself", "herself", "self",
    "additional", "voices",
}
_ANNOTATION = re.compile(r"\([^)]*\)")


def normalize_name(text):
    """Lower-case, accent-free, punctuation-free text with single spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).split())


def character_flags(character):
    """Credit annotations TMDB puts in the character string."""
    lowered = character.lower()
    return {"is_voice": "(voice)" in lowered,
            "is_uncredited": "uncredited" in lowered,
            "is_archive": "archive footage" in lowered}


def _contains(longer, shorter):
    return f" {shorter} " in f" {longer} "


def _same_character(a, b):
    if _contains(a, b) or _contains(b, a) or a.replace(" ", "") == b.replace(" ", ""):  # Mastermold
        return True
    return bool((set(a.split()) & set(b.split())) - GENERIC_WORDS)


def name_parts(tmdb_character):
    """Display names in a TMDB character string: '/'-separated, annotations removed."""
    parts = (" ".join(p.split()) for p in _ANNOTATION.sub(" ", tmdb_character).split("/"))
    return [p for p in parts if p]


def _parts(tmdb_character):
    return [normalize_name(p) for p in name_parts(tmdb_character)]


def distinctive_tokens(tmdb_character):
    """Name words that identify the character (annotations and generic words removed)."""
    return {w for p in _parts(tmdb_character) for w in p.split()} - GENERIC_WORDS


def character_matches(tmdb_character, wikidata_names):
    """True if any '/'-separated part of a TMDB character names a Wikidata name/alias."""
    parts = _parts(tmdb_character)
    names = [normalize_name(n) for n in wikidata_names]
    return any(_same_character(p, n) for p in parts if p for n in names if n)
