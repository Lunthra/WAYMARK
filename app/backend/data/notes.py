"""Private local WAYMARK notes stored in the per-user data directory."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

from app.backend.core.runtime_paths import get_data_file

NOTES_FILE = get_data_file("notes.json")


def load_notes():
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


def save_notes(notes):
    parent = os.path.dirname(NOTES_FILE)
    os.makedirs(parent, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="notes-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, NOTES_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def add_note(anime_id, episode, text):
    notes = load_notes()
    anime_key = str(anime_id)
    notes.setdefault(anime_key, []).append({
        "episode": episode,
        "text": text,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    save_notes(notes)


def get_notes(anime_id):
    return load_notes().get(str(anime_id), [])


def update_note(anime_id, note_index, new_text):
    notes = load_notes()
    anime_key = str(anime_id)
    if anime_key not in notes or not (0 <= note_index < len(notes[anime_key])):
        return False
    notes[anime_key][note_index]["text"] = new_text
    notes[anime_key][note_index]["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_notes(notes)
    return True
