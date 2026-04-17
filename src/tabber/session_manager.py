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
                        # Advanced SSH options (Tabber-only)
                        session.compression = meta.get("compression", False)
                        session.use_agent = meta.get("use_agent", True)
                        session.agent_forward = meta.get("agent_forward", False)
                        session.cert_file = meta.get("cert_file", "")
                        session.no_shell = meta.get("no_shell", False)
                        session.no_pty = meta.get("no_pty", False)
                        session.x11_forward = meta.get("x11_forward", False)
                        session.tunnels = meta.get("tunnels", [])
                        session.jump_host = meta.get("jump_host", "")
                        session.proxy_command = meta.get("proxy_command", "")
                        session.ip_version = meta.get("ip_version", "")
                        session.logical_host = meta.get("logical_host", "")
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
            "compression": session.compression,
            "use_agent": session.use_agent,
            "agent_forward": session.agent_forward,
            "cert_file": session.cert_file,
            "no_shell": session.no_shell,
            "no_pty": session.no_pty,
            "x11_forward": session.x11_forward,
            "tunnels": session.tunnels,
            "jump_host": session.jump_host,
            "proxy_command": session.proxy_command,
            "ip_version": session.ip_version,
            "logical_host": session.logical_host,
        }
        # Track group ordering
        if session.group and session.group not in metadata.get("groups_order", []):
            metadata.setdefault("groups_order", []).append(session.group)
        self._save_metadata(metadata)
