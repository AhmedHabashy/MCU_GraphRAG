"""Title types used in the tier list (docs/data_sources_and_tiers.md, "Type" column)."""

FILM = "Film"
SPECIAL = "Special"              # TV specials (e.g. Werewolf by Night): released and described like films
SEASON = "Series season"         # "Name, season N"
MOVIE_TYPES = frozenset({FILM, SPECIAL})


def is_movie(title):
    """Films and TV specials: a TMDB movie, a Wikipedia "Plot" section, one runtime."""
    return title["type"] in MOVIE_TYPES
