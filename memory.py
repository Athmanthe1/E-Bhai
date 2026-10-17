"""E-Bhai memory: one plain dict that rides in st.session_state and persists as JSON."""

import json
import os
import tempfile
from datetime import date

CAP = 200
SNIPPET = 200


def default_memory() -> dict:
    """Return a fresh default memory dict."""
    return {"profile": {"name": "", "language": "Hinglish"}, "checkins": [],
            "errors": [], "mastery": {}, "journal": []}


def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def _append(mem: dict, key: str, item: dict) -> dict:
    """Append `item` to mem[key], keeping only the newest CAP entries."""
    rows = mem.get(key)
    rows = rows if isinstance(rows, list) else []
    rows.append(item)
    mem[key] = rows[-CAP:]
    return mem


def load(path: str = "memory.json") -> dict:
    """Load memory from disk, falling back to defaults if anything is wrong."""
    fallback = default_memory()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        return fallback
    if not isinstance(raw, dict):
        return fallback
    for key, value in fallback.items():
        raw.setdefault(key, value)
    return raw


def save(mem: dict, path: str = "memory.json") -> None:
    """Write memory atomically: temp file in the same directory, then os.replace."""
    handle, temp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(mem, stream, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def add_checkin(mem: dict, mood: str, summary: str) -> dict:
    """Record a dated mood check-in."""
    return _append(mem, "checkins", {"date": _today(), "mood": mood, "summary": summary})


def add_error(mem: dict, course: str, topic: str, misconception: str, fix: str) -> dict:
    """Record a dated mistake together with its correction."""
    record = {"date": _today(), "course": course, "topic": topic,
              "misconception": misconception, "fix": fix}
    return _append(mem, "errors", record)


def update_mastery(mem: dict, topic: str, delta: int) -> dict:
    """Move a topic's mastery (new topics start at 50), clamped to 0..100."""
    table = mem.get("mastery")
    table = table if isinstance(table, dict) else {}
    base = table.get(topic, 50)
    value = base if isinstance(base, (int, float)) else 50
    table[topic] = max(0, min(100, int(value) + int(delta)))
    mem["mastery"] = table
    return mem


def add_journal(mem: dict, text: str) -> dict:
    """Append text to today's journal entry, merging same-day entries."""
    clean = (text or "").strip()
    if not clean:
        return mem
    entries = mem.get("journal")
    entries = entries if isinstance(entries, list) else []
    last = entries[-1] if entries and isinstance(entries[-1], dict) else None
    if last is not None and last.get("date") == _today():
        last["text"] = f"{last.get('text', '')}\n{clean}".strip()
    else:
        entries.append({"date": _today(), "text": clean})
    mem["journal"] = entries[-CAP:]
    return mem


def build_context(mem: dict) -> str:
    """Summarise memory as compact plain text; never raises."""
    try:
        mem = mem if isinstance(mem, dict) else {}
        profile = mem.get("profile")
        profile = profile if isinstance(profile, dict) else {}
        name = str(profile.get("name") or "a new student").strip()
        lines = [f"Student: {name} ({profile.get('language', 'Hinglish')})"]
        checkins = [c for c in (mem.get("checkins") or [])[-5:] if isinstance(c, dict)]
        lines.append("Recent check-ins: " + ("; ".join(
            f"{c.get('date')} {c.get('mood')}: {str(c.get('summary'))[:60]}" for c in checkins) or "none"))
        table = mem.get("mastery")
        table = table if isinstance(table, dict) else {}
        weak = sorted(table.items(), key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0)[:3]
        lines.append("Weakest topics: " + (", ".join(f"{t}={v}" for t, v in weak) or "none"))
        journal = [j for j in (mem.get("journal") or [])[-3:] if isinstance(j, dict)]
        lines.append("Journal: " + (" | ".join(str(j.get("text", ""))[:SNIPPET] for j in journal) or "none"))
        return "\n".join(lines)
    except Exception:
        return "No memory available yet."


def export_json(mem: dict) -> str:
    """Serialise memory to a JSON string."""
    return json.dumps(mem if isinstance(mem, dict) else default_memory(), ensure_ascii=False, indent=2)


def import_json(raw: str) -> dict:
    """Parse exported JSON into memory, falling back to defaults when invalid."""
    try:
        data = json.loads(raw)
    except Exception:
        return default_memory()
    if not isinstance(data, dict):
        return default_memory()
    for key, value in default_memory().items():
        data.setdefault(key, value)
    return data