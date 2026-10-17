"""Offline tests for memory.py: no network, no files outside tmp_path."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memory  # noqa: E402


def test_load_missing_and_corrupt(tmp_path: Path) -> None:
    """Missing, empty, corrupt and non-dict files all fall back to defaults."""
    assert memory.load(str(tmp_path / "nope.json")) == memory.default_memory()
    broken = tmp_path / "broken.json"
    for payload in ("", "{not json", "[1, 2, 3]"):
        broken.write_text(payload, encoding="utf-8")
        assert memory.load(str(broken)) == memory.default_memory()


def test_save_load_round_trip_is_atomic(tmp_path: Path) -> None:
    """Saved memory reloads unchanged and no temp file is left behind."""
    path = tmp_path / "memory.json"
    mem = memory.add_checkin(memory.default_memory(), "good", "studied algebra")
    memory.save(mem, str(path))
    assert memory.load(str(path)) == mem
    assert [item.name for item in tmp_path.iterdir()] == ["memory.json"]


def test_load_merges_missing_keys(tmp_path: Path) -> None:
    """Partial files gain the missing top-level keys."""
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"checkins": [{"date": "2024-01-01"}]}), encoding="utf-8")
    loaded = memory.load(str(path))
    assert loaded["profile"] == {"name": "", "language": "Hinglish"}
    assert len(loaded["checkins"]) == 1


def test_mastery_starts_at_50_and_clamps() -> None:
    """New topics start at 50 and the result never leaves 0..100."""
    mem = memory.update_mastery(memory.default_memory(), "algebra", 0)
    assert mem["mastery"]["algebra"] == 50
    assert memory.update_mastery(mem, "algebra", 60)["mastery"]["algebra"] == 100
    assert memory.update_mastery(mem, "algebra", -500)["mastery"]["algebra"] == 0


def test_journal_merges_same_day() -> None:
    """Same-day entries append to one record; blank text is ignored."""
    mem = memory.add_journal(memory.default_memory(), "first")
    mem = memory.add_journal(mem, "second")
    mem = memory.add_journal(mem, "   ")
    assert len(mem["journal"]) == 1
    assert mem["journal"][0]["text"] == "first\nsecond"


def test_lists_capped_at_200() -> None:
    """Only the newest 200 check-ins survive."""
    mem = memory.default_memory()
    for index in range(250):
        mem = memory.add_checkin(mem, "m", f"note {index}")
    assert len(mem["checkins"]) == 200
    assert mem["checkins"][-1]["summary"] == "note 249"


def test_build_context_empty_and_populated() -> None:
    """Context works for fresh and for populated memory."""
    empty = memory.build_context(memory.default_memory())
    assert "new student" in empty and "none" in empty
    mem = memory.default_memory()
    mem["profile"]["name"] = "Asha"
    mem = memory.add_checkin(mem, "tired", "long day")
    mem = memory.update_mastery(mem, "fractions", -20)
    mem = memory.add_journal(mem, "struggled with fractions")
    text = memory.build_context(mem)
    assert "Asha" in text and "fractions" in text and "struggled" in text


def test_import_export_round_trip_and_invalid() -> None:
    """Exported JSON reloads exactly; junk reloads as defaults."""
    mem = memory.add_error(memory.default_memory(), "math", "algebra", "sign flip", "check signs")
    assert memory.import_json(memory.export_json(mem)) == mem
    assert memory.import_json("not json") == memory.default_memory()
    assert memory.import_json("[1, 2]") == memory.default_memory()