# Tabber

A modern, native PuTTY session manager with tabbed terminals for Ubuntu.

Tabber wraps PuTTY's `plink` command-line tool in a sleek GTK4/libadwaita interface, giving you browser-like tabbed sessions, organized connection management, and powerful features for system administrators and developers.

## Features

### Core
- **Tabbed Sessions** - Open multiple SSH, Telnet, Serial, and Raw connections as tabs
- **Connection Sidebar** - Save, organize, search, and manage connections with one click
- **Quick Connect** - Type `user@host:port` or `telnet://switch:23` in the address bar and go
- **PuTTY Compatibility** - Import existing PuTTY sessions; Tabber reads and writes the same session format

### Power Features
- **Session Groups** - Organize connections into collapsible folders (Production, Staging, Dev, etc.)
- **Color-Coded Tabs** - Assign colors to connections so you never run a command on the wrong server
- **Broadcast Input** - Send keystrokes to ALL open sessions simultaneously (Ctrl+Shift+B)
- **Split Panes** - Split any tab horizontally or vertically to view two terminals side by side
- **Auto-Reconnect** - Dropped connections automatically retry up to 5 times
- **Session Logging** - Record terminal output to timestamped log files
- **Terminal Search** - Search scrollback with Ctrl+Shift+F
- **Tab Overview** - Grid view of all open tabs (Ctrl+Shift+O)
- **SFTP Transfers** - Quick upload/download dialog for SSH sessions
- **Command Snippets** - Save frequently used commands and replay them with one click

## Screenshots

*Screenshots coming soon*

## Installation

### From PPA (Ubuntu 24.04)

```bash
sudo add-apt-repository ppa:gcottrell/tabber
sudo apt update
sudo apt install tabber
```

### From Source

#### Prerequisites

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-vte-3.91 libvte-2.91-gtk4-0 putty-tools
```

#### Run

```bash
git clone https://github.com/Clanker-Built/tabber.git
cd tabber
PYTHONPATH=src python3 -m tabber
```

#### Install System-Wide

```bash
sudo pip3 install .
sudo cp data/com.github.clankerbuilt.Tabber.desktop /usr/share/applications/
sudo cp -r data/icons/hicolor/* /usr/share/icons/hicolor/
sudo gtk-update-icon-cache /usr/share/icons/hicolor
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+T | New connection |
| Ctrl+W | Close tab |
| Ctrl+L | Focus quick connect bar |
| Ctrl+PageDown | Next tab |
| Ctrl+PageUp | Previous tab |
| F9 | Toggle sidebar |
| Ctrl+Shift+C | Copy |
| Ctrl+Shift+V | Paste |
| Ctrl+Shift+F | Search in terminal |
| Ctrl+Shift+B | Toggle broadcast mode |
| Ctrl+Shift+H | Split horizontal |
| Ctrl+Shift+E | Split vertical |
| Ctrl+Shift+R | Remove split |
| Ctrl+Shift+O | Tab overview |
| Ctrl+Shift+L | Toggle logging |
| Ctrl+Shift+T | SFTP transfer |
| Ctrl+Plus | Zoom in |
| Ctrl+Minus | Zoom out |
| Ctrl+0 | Reset zoom |
| Ctrl+Q | Quit |

## Quick Connect Syntax

The quick connect bar accepts these formats:

```
myserver.com                    -> SSH to myserver.com:22
admin@10.0.0.1:2222            -> SSH as admin to 10.0.0.1:2222
telnet://switch.local:23        -> Telnet to switch.local:23
serial:///dev/ttyUSB0           -> Serial connection to /dev/ttyUSB0
```

## Configuration

Tabber stores data in two locations:

- **`~/.putty/sessions/`** - Connection details in PuTTY-compatible format
- **`~/.config/tabber/`** - Tabber metadata (groups, colors, snippets, logs)

### File Structure

```
~/.config/tabber/
    sessions.json       # Groups, colors, notes metadata
    snippets.json       # Saved command snippets
    logs/               # Session log files
```

## Supported Protocols

| Protocol | Backend | Default Port |
|----------|---------|-------------|
| SSH | plink -ssh | 22 |
| Telnet | plink -telnet | 23 |
| Rlogin | plink -rlogin | 513 |
| Raw | plink -raw | - |
| Serial | plink -serial | - |

## Building a .deb Package

```bash
sudo apt install debhelper dh-python python3-setuptools
cd tabber
dpkg-buildpackage -us -uc -b
```

The `.deb` file will be created in the parent directory.

## Tech Stack

- **Python 3.12** with PyGObject
- **GTK4** + **libadwaita 1.5** for a modern GNOME-native UI
- **VTE 3.91** for native terminal emulation
- **plink** (from putty-tools) as the connection backend

## Contributing

1. Fork the repository at [github.com/Clanker-Built/tabber](https://github.com/Clanker-Built/tabber)
2. Create a feature branch: `git checkout -b my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin my-feature`
5. Open a Pull Request

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Author

**George Cottrell** - [georgecottrell@email.com](mailto:georgecottrell@email.com)

- GitHub: [Clanker-Built](https://github.com/Clanker-Built)
- Launchpad: [gcottrell](https://launchpad.net/~gcottrell)
