# Changelog

All notable changes to Tabber will be documented in this file.

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
