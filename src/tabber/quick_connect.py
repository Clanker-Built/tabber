"""Parse quick-connect strings into Session objects."""

import re
from tabber.session import DEFAULT_PORTS, Session

# Matches: [protocol://][user@]host[:port]
_PATTERN = re.compile(
    r"^(?:(?P<protocol>ssh|telnet|rlogin|raw|serial)://)?"
    r"(?:(?P<user>[^@]+)@)?"
    r"(?P<host>[^:/]+)"
    r"(?::(?P<port>\d+))?$",
    re.IGNORECASE,
)

# Also handle serial:///dev/ttyUSB0
_SERIAL_PATTERN = re.compile(
    r"^serial://(?P<device>/\S+)$",
    re.IGNORECASE,
)


def parse_quick_connect(text):
    """Parse a quick-connect string and return a Session, or None if invalid."""
    text = text.strip()
    if not text:
        return None

    # Try serial pattern first
    m = _SERIAL_PATTERN.match(text)
    if m:
        device = m.group("device")
        return Session(
            name=f"serial:{device}",
            protocol="serial",
            serial_line=device,
        )

    # Try general pattern
    m = _PATTERN.match(text)
    if not m:
        return None

    protocol = (m.group("protocol") or "ssh").lower()
    host = m.group("host")
    user = m.group("user") or ""
    port_str = m.group("port")
    port = int(port_str) if port_str else DEFAULT_PORTS.get(protocol, 22)

    if not host:
        return None

    display_name = f"{user}@{host}" if user else host

    return Session(
        name=display_name,
        hostname=host,
        port=port,
        protocol=protocol,
        username=user,
    )
