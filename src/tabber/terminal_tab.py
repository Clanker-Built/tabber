"""Terminal tab widget with VTE + plink integration."""

import os
import time
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Vte", "3.91")

from gi.repository import Adw, Gdk, GLib, Gtk, Pango, Vte

LOG_DIR = Path.home() / ".config" / "tabber" / "logs"


class TerminalWidget(Gtk.Box):
    """A single VTE terminal with its scrollbar and search bar.

    This is the composable unit - TerminalTab can contain one or two of these
    arranged in a Gtk.Paned for split view.
    """

    def __init__(self, session, tab_parent=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        self._tab_parent = tab_parent
        self._child_pid = -1
        self._connected = False
        self._log_file = None
        self._reconnect_timer_id = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 3  # seconds

        # VTE terminal
        self.terminal = Vte.Terminal()
        self.terminal.set_scroll_on_output(False)
        self.terminal.set_scroll_on_keystroke(True)
        self.terminal.set_scrollback_lines(10000)
        self.terminal.set_font(Pango.FontDescription("Monospace 11"))
        self.terminal.set_allow_hyperlink(True)
        self.terminal.set_vexpand(True)
        self.terminal.set_hexpand(True)

        # Key controller for copy/paste and search
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.terminal.add_controller(key_controller)

        # Terminal + scrollbar
        term_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        term_box.append(self.terminal)
        scrollbar = Gtk.Scrollbar(
            orientation=Gtk.Orientation.VERTICAL,
            adjustment=self.terminal.get_vadjustment(),
        )
        term_box.append(scrollbar)
        term_box.set_vexpand(True)
        self.append(term_box)

        # Search bar (hidden by default)
        self._build_search_bar()

        self._apply_colors()

    def connect_session(self):
        """Spawn plink in the terminal."""
        argv = self._build_argv()
        self._connected = False
        self._cancel_reconnect()

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            None, argv, None,
            GLib.SpawnFlags.DEFAULT,
            None, None, -1, None,
            self._on_spawn_complete,
        )

    def disconnect(self):
        """Kill the child process if running."""
        self._cancel_reconnect()
        if self._child_pid > 0:
            try:
                os.kill(self._child_pid, 9)
            except ProcessLookupError:
                pass
        self._connected = False
        self._child_pid = -1

    def is_connected(self):
        return self._connected

    def set_font_scale(self, scale):
        self.terminal.set_font_scale(scale)

    def feed_child_text(self, text):
        """Send text to the terminal (for broadcast input)."""
        self.terminal.feed_child(text.encode("utf-8"))

    def start_logging(self):
        """Start logging terminal output to a file."""
        if self._log_file:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.session.name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"{safe_name}_{timestamp}.log"
        self._log_file = open(path, "ab")
        self.terminal.connect("commit", self._on_terminal_commit)
        return path

    def stop_logging(self):
        """Stop logging terminal output."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def set_auto_reconnect(self, enabled, delay=3, max_attempts=5):
        self._reconnect_delay = delay
        self._max_reconnect_attempts = max_attempts
        if not enabled:
            self._cancel_reconnect()

    def toggle_search(self):
        """Show/hide the search bar."""
        revealed = self._search_bar.get_search_mode()
        self._search_bar.set_search_mode(not revealed)
        if not revealed:
            self._search_entry.grab_focus()

    # --- Private ---

    def _build_search_bar(self):
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_show_close_button(True)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_margin_start(6)
        search_box.set_margin_end(6)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Search terminal...")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_text_changed)
        self._search_entry.connect("activate", self._on_search_next)
        search_box.append(self._search_entry)

        prev_btn = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous match")
        prev_btn.connect("clicked", self._on_search_prev)
        search_box.append(prev_btn)

        next_btn = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next match")
        next_btn.connect("clicked", self._on_search_next)
        search_box.append(next_btn)

        self._search_bar.set_child(search_box)
        self._search_bar.connect_entry(self._search_entry)
        self.append(self._search_bar)

    def _on_search_text_changed(self, entry):
        text = entry.get_text()
        if text:
            try:
                regex = Vte.Regex.new_for_search(
                    GLib.Regex.escape_string(text), -1, 0
                )
                self.terminal.search_set_regex(regex, 0)
            except Exception:
                pass
        else:
            self.terminal.search_set_regex(None, 0)

    def _on_search_next(self, *_args):
        self.terminal.search_find_next()

    def _on_search_prev(self, *_args):
        self.terminal.search_find_previous()

    def _build_argv(self):
        s = self.session
        if s.protocol == "serial":
            argv = ["plink", "-serial", s.serial_line or "/dev/ttyUSB0"]
            if s.serial_config:
                argv.extend(["-sercfg", s.serial_config])
            return argv

        argv = ["plink"]
        proto_flag = {
            "ssh": "-ssh", "telnet": "-telnet",
            "rlogin": "-rlogin", "raw": "-raw",
        }.get(s.protocol, "-ssh")
        argv.append(proto_flag)

        if s.port:
            argv.extend(["-P", str(s.port)])
        if s.username:
            argv.extend(["-l", s.username])
        if s.identity_file and s.protocol == "ssh":
            argv.extend(["-i", s.identity_file])
        argv.append(s.hostname)
        return argv

    def _on_spawn_complete(self, terminal, pid, error):
        if error:
            if self._tab_parent:
                self._tab_parent._show_error(f"Failed to connect: {error.message}")
            return
        self._child_pid = pid
        self._connected = True
        self._reconnect_attempts = 0
        self.terminal.connect("child-exited", self._on_child_exited)
        if self._tab_parent:
            self._tab_parent._on_terminal_connected(self)

    def _on_child_exited(self, _terminal, _status):
        self._connected = False
        self._child_pid = -1
        if self._tab_parent:
            self._tab_parent._on_terminal_disconnected(self)

        # Auto-reconnect logic
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            self._reconnect_timer_id = GLib.timeout_add_seconds(
                self._reconnect_delay, self._auto_reconnect
            )

    def _auto_reconnect(self):
        self._reconnect_timer_id = None
        if not self._connected:
            self.terminal.reset(True, True)
            self.connect_session()
        return False

    def _cancel_reconnect(self):
        if self._reconnect_timer_id:
            GLib.source_remove(self._reconnect_timer_id)
            self._reconnect_timer_id = None
        self._reconnect_attempts = 0

    def _on_terminal_commit(self, terminal, text, size):
        if self._log_file:
            try:
                self._log_file.write(text.encode("utf-8", errors="replace"))
                self._log_file.flush()
            except Exception:
                pass

    def _on_key_pressed(self, controller, keyval, keycode, state):
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if (state & ctrl_shift) == ctrl_shift:
            if keyval == Gdk.KEY_C:
                self.terminal.copy_clipboard_format(Vte.Format.TEXT)
                return True
            if keyval == Gdk.KEY_V:
                self.terminal.paste_clipboard()
                return True
            if keyval == Gdk.KEY_F:
                self.toggle_search()
                return True
        return False

    def _apply_colors(self):
        fg = Gdk.RGBA()
        fg.parse("#d0d0d0")
        bg = Gdk.RGBA()
        bg.parse("#1e1e2e")

        palette = []
        hex_colors = [
            "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#cba6f7", "#94e2d5", "#bac2de",
            "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#cba6f7", "#94e2d5", "#a6adc8",
        ]
        for hex_color in hex_colors:
            c = Gdk.RGBA()
            c.parse(hex_color)
            palette.append(c)

        self.terminal.set_colors(fg, bg, palette)

    def cleanup(self):
        """Clean up resources on tab close."""
        self._cancel_reconnect()
        self.stop_logging()
        self.disconnect()


class TerminalTab(Gtk.Box):
    """A tab containing one or two TerminalWidgets with split pane support."""

    def __init__(self, session):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        self._terminals = []
        self._paned = None
        self._split = False

        # Disconnect/reconnect banner
        self._banner = Adw.Banner()
        self._banner.set_title("Disconnected")
        self._banner.set_button_label("Reconnect")
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked", self._on_reconnect)
        self.append(self._banner)

        # Primary terminal
        self._container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._container.set_vexpand(True)
        self.append(self._container)

        self._primary = TerminalWidget(session, tab_parent=self)
        self._terminals.append(self._primary)
        self._container.append(self._primary)

    @property
    def terminal(self):
        """Return the primary terminal's VTE widget (for focus, zoom, etc.)."""
        return self._primary.terminal

    def connect_session(self):
        self._primary.connect_session()

    def is_connected(self):
        return any(t.is_connected() for t in self._terminals)

    def set_font_scale(self, scale):
        for t in self._terminals:
            t.set_font_scale(scale)

    def feed_child_text(self, text):
        """Send text to all terminals in this tab."""
        for t in self._terminals:
            if t.is_connected():
                t.feed_child_text(text)

    def get_all_terminals(self):
        """Return all TerminalWidget instances in this tab."""
        return list(self._terminals)

    def split_horizontal(self, session=None):
        """Split this tab horizontally (top/bottom)."""
        self._do_split(Gtk.Orientation.VERTICAL, session)

    def split_vertical(self, session=None):
        """Split this tab vertically (left/right)."""
        self._do_split(Gtk.Orientation.HORIZONTAL, session)

    def unsplit(self):
        """Remove the split, keeping only the primary terminal."""
        if not self._split:
            return
        # Remove secondary terminal
        secondary = self._terminals[1] if len(self._terminals) > 1 else None
        if secondary:
            secondary.cleanup()
            self._terminals.remove(secondary)

        # Replace paned with just the primary
        self._container.remove(self._paned)
        self._paned = None
        self._container.append(self._primary)
        self._split = False

    def start_logging(self):
        paths = []
        for t in self._terminals:
            p = t.start_logging()
            if p:
                paths.append(str(p))
        return paths

    def stop_logging(self):
        for t in self._terminals:
            t.stop_logging()

    def toggle_search(self):
        """Toggle search on the focused (or primary) terminal."""
        self._primary.toggle_search()

    def cleanup(self):
        for t in self._terminals:
            t.cleanup()

    # --- Private ---

    def _do_split(self, orientation, session=None):
        if self._split:
            return  # Already split

        session = session or self.session
        secondary = TerminalWidget(session, tab_parent=self)
        self._terminals.append(secondary)

        # Remove primary from container
        self._container.remove(self._primary)

        # Create paned
        self._paned = Gtk.Paned(orientation=orientation)
        self._paned.set_vexpand(True)
        self._paned.set_start_child(self._primary)
        self._paned.set_end_child(secondary)
        self._paned.set_resize_start_child(True)
        self._paned.set_resize_end_child(True)
        self._paned.set_shrink_start_child(False)
        self._paned.set_shrink_end_child(False)
        self._container.append(self._paned)

        secondary.connect_session()
        self._split = True

    def _show_error(self, message):
        self._banner.set_title(message)
        self._banner.set_revealed(True)

    def _on_terminal_connected(self, terminal_widget):
        self._banner.set_revealed(False)
        # Update tab title
        tab_view = self._find_tab_view()
        if tab_view:
            page = tab_view.get_page(self)
            if page:
                title = page.get_title().replace(" (disconnected)", "").replace(" (reconnecting...)", "")
                page.set_title(title)

    def _on_terminal_disconnected(self, terminal_widget):
        # Check if ALL terminals in this tab are disconnected
        if not any(t.is_connected() for t in self._terminals):
            if terminal_widget._reconnect_attempts < terminal_widget._max_reconnect_attempts:
                self._banner.set_title(
                    f"Reconnecting... (attempt {terminal_widget._reconnect_attempts}/{terminal_widget._max_reconnect_attempts})"
                )
                self._banner.set_button_label("Stop")
                self._banner.set_revealed(True)
            else:
                self._banner.set_title("Session disconnected")
                self._banner.set_button_label("Reconnect")
                self._banner.set_revealed(True)

            tab_view = self._find_tab_view()
            if tab_view:
                page = tab_view.get_page(self)
                if page:
                    title = page.get_title()
                    for suffix in (" (disconnected)", " (reconnecting...)"):
                        title = title.replace(suffix, "")
                    if terminal_widget._reconnect_attempts < terminal_widget._max_reconnect_attempts:
                        page.set_title(f"{title} (reconnecting...)")
                    else:
                        page.set_title(f"{title} (disconnected)")

    def _on_reconnect(self, _banner):
        for t in self._terminals:
            t._cancel_reconnect()
            if not t.is_connected():
                t._reconnect_attempts = 0
                t.terminal.reset(True, True)
                t.connect_session()

    def _find_tab_view(self):
        widget = self.get_parent()
        while widget is not None:
            if isinstance(widget, Adw.TabView):
                return widget
            widget = widget.get_parent()
        return None
