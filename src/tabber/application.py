"""Main application class."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

from pathlib import Path

from gi.repository import Adw, Gio, Gtk

from tabber import APP_ID, __version__


class TabberApplication(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._setup_icon_theme()
        self._setup_actions()
        # Default to dark mode - terminal apps look best dark
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def _setup_icon_theme(self):
        """Add the local data/icons directory to the icon search path
        so the custom icon works before system-wide installation."""
        from gi.repository import Gdk
        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            # Check for icons relative to the source tree
            src_dir = Path(__file__).resolve().parent.parent.parent
            icons_dir = src_dir / "data" / "icons"
            if icons_dir.exists():
                icon_theme.add_search_path(str(icons_dir))

    def do_activate(self):
        win = self.props.active_window
        if not win:
            from tabber.window import TabberWindow
            win = TabberWindow(application=self)
            win.set_help_overlay(self._build_shortcuts_window())
        win.present()

    def _build_shortcuts_window(self):
        shortcuts = Gtk.ShortcutsWindow()
        section = Gtk.ShortcutsSection(title="Tabber", section_name="tabber")
        section.set_visible(True)

        groups = [
            ("Sessions", [
                ("New Connection", "<Control>t"),
                ("Quick Connect", "<Control>l"),
                ("Close Tab", "<Control>w"),
                ("Tab Overview", "<Control><Shift>o"),
            ]),
            ("Navigation", [
                ("Next Tab", "<Control>Page_Down"),
                ("Previous Tab", "<Control>Page_Up"),
                ("Toggle Sidebar", "F9"),
            ]),
            ("Terminal", [
                ("Copy", "<Control><Shift>c"),
                ("Paste", "<Control><Shift>v"),
                ("Search in Terminal", "<Control><Shift>f"),
                ("Zoom In", "<Control>plus"),
                ("Zoom Out", "<Control>minus"),
                ("Zoom Reset", "<Control>0"),
            ]),
            ("Split Panes", [
                ("Split Horizontal", "<Control><Shift>h"),
                ("Split Vertical", "<Control><Shift>e"),
                ("Remove Split", "<Control><Shift>r"),
            ]),
            ("Features", [
                ("Toggle Broadcast", "<Control><Shift>b"),
                ("Start/Stop Logging", "<Control><Shift>l"),
                ("SFTP Transfer", "<Control><Shift>t"),
            ]),
            ("Application", [
                ("Quit", "<Control>q"),
            ]),
        ]

        for group_title, items in groups:
            group = Gtk.ShortcutsGroup(title=group_title)
            group.set_visible(True)
            for title, accel in items:
                shortcut = Gtk.ShortcutsShortcut(title=title, accelerator=accel)
                shortcut.set_visible(True)
                group.add_shortcut(shortcut)
            section.add_group(group)

        shortcuts.add_section(section)
        return shortcuts

    def _setup_actions(self):
        actions = [
            ("quit", self._on_quit, ["<Control>q"]),
            ("about", self._on_about, None),
            ("new-tab", self._on_new_tab, ["<Control>t"]),
            ("close-tab", self._on_close_tab, ["<Control>w"]),
            ("toggle-sidebar", self._on_toggle_sidebar, ["F9"]),
            ("focus-quick-connect", self._on_focus_quick_connect, ["<Control>l"]),
            ("next-tab", self._on_next_tab, ["<Control>Page_Down"]),
            ("prev-tab", self._on_prev_tab, ["<Control>Page_Up"]),
            ("zoom-in", self._on_zoom_in, ["<Control>plus", "<Control>equal"]),
            ("zoom-out", self._on_zoom_out, ["<Control>minus"]),
            ("zoom-reset", self._on_zoom_reset, ["<Control>0"]),
            # Phase 2
            ("tab-overview", self._on_tab_overview, ["<Control><Shift>o"]),
            ("split-horizontal", self._on_split_h, ["<Control><Shift>h"]),
            ("split-vertical", self._on_split_v, ["<Control><Shift>e"]),
            ("unsplit", self._on_unsplit, ["<Control><Shift>r"]),
            ("toggle-broadcast", self._on_toggle_broadcast, ["<Control><Shift>b"]),
            ("search-terminal", self._on_search_terminal, ["<Control><Shift>f"]),
            ("toggle-logging", self._on_toggle_logging, ["<Control><Shift>l"]),
            ("sftp-transfer", self._on_sftp_transfer, ["<Control><Shift>t"]),
        ]
        for name, callback, accels in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

    def _get_window(self):
        return self.props.active_window

    def _on_quit(self, *_args):
        self.quit()

    def _on_about(self, *_args):
        about = Adw.AboutDialog(
            application_name="Tabber",
            application_icon=APP_ID,
            version=__version__,
            developer_name="George Cottrell",
            license_type=Gtk.License.GPL_3_0,
            comments="A modern PuTTY session manager with tabbed terminals "
                     "for Ubuntu. Features tabbed sessions, split panes, "
                     "broadcast input, session groups, SFTP transfers, "
                     "command snippets, terminal search, session logging, "
                     "and auto-reconnect.",
            website="https://github.com/Clanker-Built/tabber",
            issue_url="https://github.com/Clanker-Built/tabber/issues",
            developers=["George Cottrell <georgecottrell@email.com>"],
            copyright="Copyright 2026 George Cottrell",
        )
        about.present(self._get_window())

    def _on_new_tab(self, *_args):
        win = self._get_window()
        if win:
            win.show_connection_dialog()

    def _on_close_tab(self, *_args):
        win = self._get_window()
        if win:
            win.close_current_tab()

    def _on_toggle_sidebar(self, *_args):
        win = self._get_window()
        if win:
            win.toggle_sidebar()

    def _on_focus_quick_connect(self, *_args):
        win = self._get_window()
        if win:
            win.focus_quick_connect()

    def _on_next_tab(self, *_args):
        win = self._get_window()
        if win:
            win.next_tab()

    def _on_prev_tab(self, *_args):
        win = self._get_window()
        if win:
            win.prev_tab()

    def _on_zoom_in(self, *_args):
        win = self._get_window()
        if win:
            win.zoom_in()

    def _on_zoom_out(self, *_args):
        win = self._get_window()
        if win:
            win.zoom_out()

    def _on_zoom_reset(self, *_args):
        win = self._get_window()
        if win:
            win.zoom_reset()

    # Phase 2 handlers

    def _on_tab_overview(self, *_args):
        win = self._get_window()
        if win:
            win._tab_overview.set_open(not win._tab_overview.get_open())

    def _on_split_h(self, *_args):
        win = self._get_window()
        if win:
            win._on_split_horizontal()

    def _on_split_v(self, *_args):
        win = self._get_window()
        if win:
            win._on_split_vertical()

    def _on_unsplit(self, *_args):
        win = self._get_window()
        if win:
            win._on_unsplit()

    def _on_toggle_broadcast(self, *_args):
        win = self._get_window()
        if win:
            win.set_broadcast_mode(not win._broadcast_mode)

    def _on_search_terminal(self, *_args):
        win = self._get_window()
        if win:
            win.search_terminal()

    def _on_toggle_logging(self, *_args):
        win = self._get_window()
        if win:
            tab = win._get_current_tab()
            if tab:
                # Toggle: check if any terminal is logging
                terminals = tab.get_all_terminals()
                if any(t._log_file for t in terminals):
                    tab.stop_logging()
                    win.show_toast("Logging stopped")
                else:
                    paths = tab.start_logging()
                    if paths:
                        win.show_toast(f"Logging to {paths[0]}")

    def _on_sftp_transfer(self, *_args):
        win = self._get_window()
        if win:
            win._on_sftp_transfer()
