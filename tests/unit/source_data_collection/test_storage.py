"""Unit tests for src/source_data_collection/storage.py."""

from src.source_data_collection.storage import read_csv, read_json, write_csv, write_json


def test_csv_round_trip_creates_parent_folders(tmp_path):
    path = tmp_path / "a" / "b.csv"
    write_csv(path, [{"title": "Loki, season 1", "n": 1}])
    assert read_csv(path) == [{"title": "Loki, season 1", "n": "1"}]


def test_json_round_trip_keeps_unicode(tmp_path):
    path = tmp_path / "x" / "c.json"
    write_json(path, {"name": "Zoë"})
    assert read_json(path) == {"name": "Zoë"}
    assert "Zoë" in path.read_text(encoding="utf-8")
