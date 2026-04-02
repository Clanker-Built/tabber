"""Session data model and PuTTY file I/O."""

import os
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

PUTTY_DIR = Path.home() / ".putty"
PUTTY_SESSIONS_DIR = PUTTY_DIR / "sessions"

# Default ports per protocol
DEFAULT_PORTS = {
    "ssh": 22,
    "telnet": 23,
    "rlogin": 513,
    "raw": 0,
    "serial": 0,
}

PROTOCOL_ICONS = {
    "ssh": "network-server-symbolic",
    "telnet": "network-workgroup-symbolic",
    "rlogin": "network-workgroup-symbolic",
    "raw": "network-transmit-symbolic",
    "serial": "media-removable-symbolic",
}


@dataclass
class Session:
    name: str = ""
    hostname: str = ""
    port: int = 22
    protocol: str = "ssh"
    username: str = ""
    identity_file: str = ""
    # Tabber metadata (stored in sessions.json, not PuTTY files)
    group: str = ""
    color: str = ""
    notes: str = ""
    last_connected: str = ""
    # Serial-specific
    serial_line: str = ""
    serial_config: str = ""

    @property
    def protocol_icon(self):
        return PROTOCOL_ICONS.get(self.protocol, "network-server-symbolic")

    @property
    def connection_string(self):
        if self.protocol == "serial":
            return f"serial://{self.serial_line}"
        parts = []
        if self.protocol != "ssh":
            parts.append(f"{self.protocol}://")
        if self.username:
            parts.append(f"{self.username}@")
        parts.append(self.hostname)
        default_port = DEFAULT_PORTS.get(self.protocol, 22)
        if self.port and self.port != default_port:
            parts.append(f":{self.port}")
        return "".join(parts)

    def copy(self):
        """Return a shallow copy."""
        return Session(**self.__dict__)


def _url_encode_name(name):
    """Encode a session name for PuTTY filename (spaces -> %20, etc.)."""
    return urllib.parse.quote(name, safe="")


def _url_decode_name(filename):
    """Decode a PuTTY session filename back to a name."""
    return urllib.parse.unquote(filename)


# PuTTY protocol name mapping
_PUTTY_PROTOCOL_MAP = {
    "ssh": "ssh",
    "telnet": "telnet",
    "rlogin": "rlogin",
    "raw": "raw",
    "serial": "serial",
}

_PUTTY_PROTOCOL_REVERSE = {v: k for k, v in _PUTTY_PROTOCOL_MAP.items()}


def read_putty_session(filepath):
    """Read a PuTTY session file and return a Session object."""
    name = _url_decode_name(filepath.name)
    data = {}
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, _, value = line.partition("=")
                    data[key] = value
    except OSError:
        return None

    protocol = _PUTTY_PROTOCOL_REVERSE.get(data.get("Protocol", "ssh"), "ssh")
    port_str = data.get("PortNumber", str(DEFAULT_PORTS.get(protocol, 22)))

    return Session(
        name=name,
        hostname=data.get("HostName", ""),
        port=int(port_str) if port_str.isdigit() else DEFAULT_PORTS.get(protocol, 22),
        protocol=protocol,
        username=data.get("UserName", ""),
        identity_file=data.get("PublicKeyFile", ""),
        serial_line=data.get("SerialLine", ""),
        serial_config=data.get("SerialSpeed", ""),
    )


def write_putty_session(session):
    """Write a Session object to a PuTTY session file."""
    PUTTY_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PUTTY_SESSIONS_DIR / _url_encode_name(session.name)

    protocol = _PUTTY_PROTOCOL_MAP.get(session.protocol, "ssh")
    port = session.port or DEFAULT_PORTS.get(session.protocol, 22)

    # Write a minimal but valid PuTTY session file
    lines = [
        f"Protocol={protocol}",
        f"HostName={session.hostname}",
        f"PortNumber={port}",
        f"UserName={session.username}",
    ]
    if session.identity_file:
        lines.append(f"PublicKeyFile={session.identity_file}")
    if session.protocol == "serial":
        lines.append(f"SerialLine={session.serial_line}")
        if session.serial_config:
            lines.append(f"SerialSpeed={session.serial_config}")

    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")


def delete_putty_session(name):
    """Delete a PuTTY session file."""
    filepath = PUTTY_SESSIONS_DIR / _url_encode_name(name)
    try:
        filepath.unlink()
    except FileNotFoundError:
        pass


def list_putty_sessions():
    """Return a list of session names from ~/.putty/sessions/."""
    if not PUTTY_SESSIONS_DIR.exists():
        return []
    return [_url_decode_name(f.name) for f in PUTTY_SESSIONS_DIR.iterdir() if f.is_file()]
