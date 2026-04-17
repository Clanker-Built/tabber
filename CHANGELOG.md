# Changelog

All notable changes to Tabber will be documented in this file.

## [0.1.5] - 2026-04-16

### Added
- Detach a tab to a new window: right-click a tab > Move to New Window,
  drag a tab onto the desktop, or Ctrl+Shift+D on the active tab
- Tabbed connection dialog organized into five sections:
  - **Quick Connect** – name, protocol, host, port, user, SSH key
  - **SSH** – compression (`-C`), X11 forwarding (`-X`), no-PTY (`-T`),
    no-shell (`-N`), Pageant agent (`-agent`), agent forwarding (`-A`),
    certificate file (`-cert`)
  - **Tunnels** – editable list of Local (`-L`), Remote (`-R`), and
    Dynamic SOCKS (`-D`) port forwards
  - **Proxy / Network** – jump host (`-J`), proxy command (`-proxycmd`),
    IPv4/IPv6 forcing, logical host name (`-loghost`)
  - **Terminal** – group, tab color, notes
- Advanced session options persist in Tabber's JSON metadata; basic
  fields remain compatible with PuTTY's session format

## [0.1.4] - 2026-04-16

### Fixed
- Closing tabs is now instant. The `close-page` handler called a
  nonexistent `Adw.TabView.confirm_close_page` method, raising
  `AttributeError` on every close and triggering GTK's default close
  path on top of the explicit `close_page_finish` call
- Cancel auto-reconnect timer on tab close so a destroyed terminal
  widget can't attempt a reconnect three seconds later

## [0.1.3] - 2026-04-02

### Added
- Connect button (play icon) on each sidebar session row
- Right-click context menu on sessions: Connect, Edit, Delete
- Right-click context menu on group folders: Connect All, Add Connection
- **Connect All** opens tabs for every session in a group at once
- **Add Connection** pre-fills the group name in the new connection dialog

### Fixed
- Clicking a session inside a group folder now connects correctly
  instead of selecting the whole group

## [0.1.2] - 2026-04-02

### Added
- Dark mode with appearance menu (Dark, Light, Follow System)
- Default to dark theme on startup

## [0.1.1] - 2026-04-02

### Fixed
- PPA build failure: added `pybuild-plugin-pyproject` to Build-Depends

## [0.1.0] - 2026-04-02

### Added
- Tabbed terminal sessions using VTE 3.91 and plink
- Left sidebar with saved connections organized into collapsible groups
- Quick connect bar supporting `[protocol://][user@]host[:port]` syntax
- Connection dialog for creating and editing saved sessions
- Support for SSH, Telnet, Rlogin, Raw, and Serial protocols
- PuTTY session import from `~/.putty/sessions/`
- Split panes: horizontal and vertical splits within a single tab
- Broadcast input mode to send keystrokes to all open sessions
- Color-coded tabs and sidebar indicators (Red, Orange, Yellow, Green, Blue, Purple)
- Auto-reconnect with configurable retry attempts on disconnection
- Session logging to `~/.config/tabber/logs/`
- Terminal search with regex support (Ctrl+Shift+F)
- Tab overview grid view (Ctrl+Shift+O)
- SFTP file transfer dialog for SSH sessions
- Command snippets library for saving and replaying frequent commands
- Full keyboard shortcut support with shortcuts window
- Catppuccin-inspired terminal color scheme
- Dark and light theme support via libadwaita
- PuTTY-compatible session file format for interoperability
- Desktop integration with `.desktop` file and app icon
