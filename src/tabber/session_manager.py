"""Session manager: CRUD operations, import/export, metadata persistence."""

import json
from pathlib import Path

from tabber.session import (
    PUTTY_SESSIONS_DIR,
    Session,
    delete_putty_session,
    list_putty_sessions,
    read_putty_session,
    write_putty_session,
    _url_encode_name,
)

CONFIG_DIR = Path.home() / ".config" / "tabber"
METADATA_FILE = CONFIG_DIR / "sessions.json"


class SessionManager:

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load_all(self):
        """Load all sessions from PuTTY files + Tabber metadata."""
        metadata = self._load_metadata()
        sessions = []

        # Load from PuTTY session files
        if PUTTY_SESSIONS_DIR.exists():
            for f in PUTTY_SESSIONS_DIR.iterdir():
                if f.is_file():
                    session = read_putty_session(f)
                    if session:
                        # Merge Tabber metadata
                        meta = metadata.get("sessions", {}).get(session.name, {})
                        session.group = meta.get("group", "")
                        session.color = meta.get("color", "")
                        session.notes = meta.get("notes", "")
                        session.last_connected = meta.get("last_connected", "")
                        sessions.append(session)

        return sessions

    def save_session(self, session):
        """Save a session to PuTTY file format and update Tabber metadata."""
        write_putty_session(session)
        self._update_metadata(session)

    def delete_session(self, name):
        """Delete a session from both PuTTY files and Tabber metadata."""
        delete_putty_session(name)
        metadata = self._load_metadata()
        metadata.get("sessions", {}).pop(name, None)
        self._save_metadata(metadata)

    def rename_session(self, old_name, new_name):
        """Rename a session (delete old, save new)."""
        sessions = self.load_all()
        for s in sessions:
            if s.name == old_name:
                delete_putty_session(old_name)
                s.name = new_name
                self.save_session(s)
                # Move metadata
                metadata = self._load_metadata()
                meta = metadata.get("sessions", {}).pop(old_name, {})
                metadata.setdefault("sessions", {})[new_name] = meta
                self._save_metadata(metadata)
                return s
        return None

    def import_putty_sessions(self):
        """Import PuTTY sessions that aren't already tracked in Tabber metadata."""
        metadata = self._load_metadata()
        tracked = set(metadata.get("sessions", {}).keys())
        putty_names = list_putty_sessions()
        count = 0

        for name in putty_names:
            if name not in tracked:
                filepath = PUTTY_SESSIONS_DIR / _url_encode_name(name)
                session = read_putty_session(filepath)
                if session and session.hostname:
                    self._update_metadata(session)
                    count += 1

        return count

    def update_last_connected(self, name):
        """Update the last_connected timestamp for a session."""
        from datetime import datetime, timezone
        metadata = self._load_metadata()
        metadata.setdefault("sessions", {}).setdefault(name, {})
        metadata["sessions"][name]["last_connected"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata(metadata)

    def _load_metadata(self):
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"version": 1, "sessions": {}, "groups_order": []}

    def _save_metadata(self, metadata):
        with open(METADATA_FILE, "w") as f:
            json.dump(metadata, f, indent=2)

    def _update_metadata(self, session):
        metadata = self._load_metadata()
        metadata.setdefault("sessions", {})[session.name] = {
            "group": session.group,
            "color": session.color,
            "notes": session.notes,
            "last_connected": session.last_connected,
        }
        # Track group ordering
        if session.group and session.group not in metadata.get("groups_order", []):
            metadata.setdefault("groups_order", []).append(session.group)
        self._save_metadata(metadata)
