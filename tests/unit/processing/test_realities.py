"""Unit tests for src/processing/realities.py."""

from src.processing.realities import MCU, marvel_db_page_of, reality_of_marvel_db_earth


def test_the_main_mcu_is_earth_616():
    assert MCU == "Earth-616"


def test_marvel_database_mcu_page_maps_to_earth_616():
    assert reality_of_marvel_db_earth("Earth-199999") == "Earth-616"


def test_marvel_database_comics_earth_616_is_out_of_scope():
    assert reality_of_marvel_db_earth("Earth-616") == ""


def test_other_marvel_database_earths_keep_their_name():
    assert reality_of_marvel_db_earth("Earth-828") == "Earth-828"
    assert reality_of_marvel_db_earth("Multiverse") == "Multiverse"
    assert reality_of_marvel_db_earth("") == ""


def test_marvel_database_page_of_a_reality():
    assert marvel_db_page_of("Earth-616") == "Earth-199999"
    assert marvel_db_page_of("Earth-10005") == "Earth-10005"
