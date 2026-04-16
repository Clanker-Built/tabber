"""Main application window with all Phase 2 features."""

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from tabber.terminal_tab import TerminalTab


# Color definitions for color-coded tabs
TAB_COLORS = {
    "red": "#e01b24",
    "orange": "#ff7800",
    "yellow": "#f5c211",
    "green": "#33d17a",
    "blue": "#3584e4",
    "purple": "#9141ac",
}


class TabberWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(
            default_width=1100,
            default_height=700,
            title="Tabber",
            **kwargs,
        )
        self._font_scale = 1.0
        self._broadcast_mode = False
        self._broadcast_targets = []  # list of TerminalTab references
        self._build_ui()
        self.refresh_sidebar()

    def _build_ui(self):
        # Root: toast overlay for notifications
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        # Tab overview wraps everything for grid view (Ctrl+Shift+O)
        self._tab_overview = Adw.TabOverview()
        self._tab_overview.set_enable_new_tab(True)
        self._tab_overview.connect("create-tab", self._on_overview_create_tab)
        self._toast_overlay.set_child(self._tab_overview)

        # Main split: sidebar + content
        self._split_view = Adw.OverlaySplitView()
        self._split_view.set_show_sidebar(True)
        self._split_view.set_min_sidebar_width(220)
        self._split_view.set_max_sidebar_width(360)
        self._tab_overview.set_child(self._split_view)

        self._build_sidebar()
        self._build_content()

    def _build_sidebar(self):
        sidebar_toolbar = Adw.ToolbarView()
        self._split_view.set_sidebar(sidebar_toolbar)

        # Sidebar header
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_title(True)
        sidebar_title = Gtk.Label(label="Connections")
        sidebar_title.add_css_class("heading")
        sidebar_header.set_title_widget(sidebar_title)

        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New Connection")
        add_btn.connect("clicked", self._on_add_connection)
        sidebar_header.pack_start(add_btn)

        import_btn = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Import PuTTY Sessions")
        import_btn.connect("clicked", self._on_import_sessions)
        sidebar_header.pack_end(import_btn)

        sidebar_toolbar.add_top_bar(sidebar_header)

        # Search + session list + snippets panel in a notebook-like stack
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # View switcher: Connections / Snippets
        self._sidebar_stack = Gtk.Stack()
        self._sidebar_stack.set_vexpand(True)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self._sidebar_stack)
        switcher.set_margin_start(6)
        switcher.set_margin_end(6)
        switcher.set_margin_top(4)
        switcher.set_margin_bottom(4)
        sidebar_box.append(switcher)

        # --- Connections page ---
        connections_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Filter connections...")
        self._search_entry.set_margin_start(6)
        self._search_entry.set_margin_end(6)
        self._search_entry.set_margin_top(2)
        self._search_entry.set_margin_bottom(2)
        self._search_entry.connect("search-changed", self._on_search_changed)
        connections_page.append(self._search_entry)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._session_listbox = Gtk.ListBox()
        self._session_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._session_listbox.add_css_class("navigation-sidebar")
        self._session_listbox.set_placeholder(
            Gtk.Label(label="No saved connections\nClick + to add one", margin_top=20, opacity=0.5)
        )
        self._session_listbox.connect("row-activated", self._on_session_activated)
        scroll.set_child(self._session_listbox)
        connections_page.append(scroll)

        self._sidebar_stack.add_titled(connections_page, "connections", "Connections")

        # --- Snippets page ---
        from tabber.snippets import SnippetsPanel
        self._snippets_panel = SnippetsPanel()
        self._snippets_panel.connect("snippet-activated", self._on_snippet_activated)
        self._sidebar_stack.add_titled(self._snippets_panel, "snippets", "Snippets")

        sidebar_box.append(self._sidebar_stack)
        sidebar_toolbar.set_content(sidebar_box)

    def _build_content(self):
        content_toolbar = Adw.ToolbarView()
        self._split_view.set_content(content_toolbar)

        # Content header
        header = Adw.HeaderBar()

        # Sidebar toggle
        toggle_btn = Gtk.Button(icon_name="sidebar-show-symbolic", tooltip_text="Toggle Sidebar (F9)")
        toggle_btn.connect("clicked", lambda _: self.toggle_sidebar())
        header.pack_start(toggle_btn)

        # Broadcast mode toggle
        self._broadcast_btn = Gtk.ToggleButton(icon_name="network-transmit-symbolic",
                                                tooltip_text="Broadcast Mode (send input to all tabs)")
        self._broadcast_btn.connect("toggled", self._on_broadcast_toggled)
        header.pack_start(self._broadcast_btn)

        # Quick connect entry in the center
        self._quick_connect = Gtk.Entry()
        self._quick_connect.set_placeholder_text("Quick connect: [protocol://]user@host[:port]")
        self._quick_connect.set_hexpand(True)
        self._quick_connect.set_max_width_chars(60)
        self._quick_connect.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "network-server-symbolic")
        self._quick_connect.connect("activate", self._on_quick_connect)
        clamp = Adw.Clamp(maximum_size=600, child=self._quick_connect)
        header.set_title_widget(clamp)

        # Tab overview button
        overview_btn = Gtk.Button(icon_name="view-grid-symbolic", tooltip_text="Tab Overview")
        overview_btn.connect("clicked", lambda _: self._tab_overview.set_open(True))
        header.pack_end(overview_btn)

        # Hamburger menu
        menu = Gio.Menu()

        session_menu = Gio.Menu()
        session_menu.append("Import PuTTY Sessions", "win.import-sessions")
        menu.append_section(None, session_menu)

        tab_menu = Gio.Menu()
        tab_menu.append("Split Horizontally", "win.split-horizontal")
        tab_menu.append("Split Vertically", "win.split-vertical")
        tab_menu.append("Unsplit", "win.unsplit")
        menu.append_section("Split Pane", tab_menu)

        log_menu = Gio.Menu()
        log_menu.append("Start Logging", "win.start-logging")
        log_menu.append("Stop Logging", "win.stop-logging")
        menu.append_section("Logging", log_menu)

        transfer_menu = Gio.Menu()
        transfer_menu.append("SFTP Transfer...", "win.sftp-transfer")
        menu.append_section(None, transfer_menu)

        appearance_menu = Gio.Menu()
        appearance_menu.append("Dark Mode", "win.dark-mode")
        appearance_menu.append("Light Mode", "win.light-mode")
        appearance_menu.append("Follow System", "win.system-mode")
        menu.append_section("Appearance", appearance_menu)

        other_menu = Gio.Menu()
        other_menu.append("Keyboard Shortcuts", "win.show-help-overlay")
        other_menu.append("About Tabber", "app.about")
        menu.append_section(None, other_menu)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu")
        header.pack_end(menu_btn)

        content_toolbar.add_top_bar(header)

        # Broadcast info bar (shown when broadcast mode is active)
        self._broadcast_bar = Adw.Banner()
        self._broadcast_bar.set_title("Broadcast Mode: input is sent to ALL open terminals")
        self._broadcast_bar.set_button_label("Turn Off")
        self._broadcast_bar.set_revealed(False)
        self._broadcast_bar.connect("button-clicked", self._on_broadcast_off)

        # Tab bar + tab view
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(self._broadcast_bar)

        self._tab_view = Adw.TabView()
        self._tab_view.connect("close-page", self._on_close_page)
        self._tab_view.connect("notify::selected-page", self._on_tab_selected)
        self._tab_view.connect("notify::n-pages", self._on_tab_count_changed)

        # Connect tab overview to tab view
        self._tab_overview.set_view(self._tab_view)

        self._tab_bar = Adw.TabBar()
        self._tab_bar.set_view(self._tab_view)
        self._tab_bar.set_autohide(False)
        self._tab_bar.set_expand_tabs(True)

        content_box.append(self._tab_bar)

        # Stack for empty state vs tabs
        self._content_stack = Gtk.Stack()
        self._content_stack.set_vexpand(True)

        empty_state = Adw.StatusPage(
            icon_name="network-server-symbolic",
            title="No Active Sessions",
            description="Connect from the sidebar or use Quick Connect (Ctrl+L)\n\nCtrl+T  New Connection  |  F9  Toggle Sidebar",
        )
        self._content_stack.add_named(empty_state, "empty")
        self._content_stack.add_named(self._tab_view, "tabs")
        self._content_stack.set_visible_child_name("empty")

        content_box.append(self._content_stack)
        content_toolbar.set_content(content_box)

        # Register window actions
        self._register_window_actions()

        # CSS for color-coded tab indicators
        self._setup_css()

    def _register_window_actions(self):
        simple_actions = [
            ("import-sessions", self._on_import_sessions),
            ("split-horizontal", self._on_split_horizontal),
            ("split-vertical", self._on_split_vertical),
            ("unsplit", self._on_unsplit),
            ("start-logging", self._on_start_logging),
            ("stop-logging", self._on_stop_logging),
            ("sftp-transfer", self._on_sftp_transfer),
            ("search-terminal", self._on_search_terminal),
            ("dark-mode", self._on_dark_mode),
            ("light-mode", self._on_light_mode),
            ("system-mode", self._on_system_mode),
        ]
        for name, callback in simple_actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _setup_css(self):
        css = b"""
        .broadcast-active {
            border-top: 2px solid @warning_color;
        }
        .tab-color-indicator {
            min-width: 8px;
            min-height: 8px;
            border-radius: 50%;
            margin: 0 4px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # === Public API ===

    def open_session_tab(self, session):
        """Open a new tab for the given Session object."""
        tab = TerminalTab(session)
        page = self._tab_view.append(tab)
        page.set_title(session.name or session.hostname)
        page.set_icon(Gio.ThemedIcon.new(session.protocol_icon))
        page.set_tooltip(session.connection_string)

        # Color-coded tab indicator
        if session.color and session.color in TAB_COLORS:
            indicator = Gio.ThemedIcon.new("radio-symbolic")
            page.set_indicator_icon(indicator)
            page.set_indicator_activatable(False)

        self._tab_view.set_selected_page(page)
        tab.connect_session()
        self._content_stack.set_visible_child_name("tabs")
        return page

    def show_connection_dialog(self, session=None):
        from tabber.connection_dialog import ConnectionDialog
        dialog = ConnectionDialog(session=session, transient_for=self)
        dialog.connect("session-saved", self._on_session_saved)
        dialog.present(self)

    def close_current_tab(self):
        page = self._tab_view.get_selected_page()
        if page:
            self._tab_view.close_page(page)

    def toggle_sidebar(self):
        self._split_view.set_show_sidebar(not self._split_view.get_show_sidebar())

    def focus_quick_connect(self):
        self._quick_connect.grab_focus()

    def next_tab(self):
        if self._tab_view.get_n_pages() < 2:
            return
        page = self._tab_view.get_selected_page()
        pos = self._tab_view.get_page_position(page)
        next_pos = (pos + 1) % self._tab_view.get_n_pages()
        self._tab_view.set_selected_page(self._tab_view.get_nth_page(next_pos))

    def prev_tab(self):
        if self._tab_view.get_n_pages() < 2:
            return
        page = self._tab_view.get_selected_page()
        pos = self._tab_view.get_page_position(page)
        prev_pos = (pos - 1) % self._tab_view.get_n_pages()
        self._tab_view.set_selected_page(self._tab_view.get_nth_page(prev_pos))

    def zoom_in(self):
        self._font_scale = min(self._font_scale + 0.1, 3.0)
        self._apply_zoom()

    def zoom_out(self):
        self._font_scale = max(self._font_scale - 0.1, 0.3)
        self._apply_zoom()

    def zoom_reset(self):
        self._font_scale = 1.0
        self._apply_zoom()

    def search_terminal(self):
        page = self._tab_view.get_selected_page()
        if page:
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                tab.toggle_search()

    def refresh_sidebar(self):
        """Reload sessions into the sidebar, grouped by folder."""
        from tabber.session_manager import SessionManager
        manager = SessionManager()
        sessions = manager.load_all()

        # Clear existing rows
        while True:
            row = self._session_listbox.get_row_at_index(0)
            if row is None:
                break
            self._session_listbox.remove(row)

        # Group sessions
        groups = {}
        ungrouped = []
        for session in sorted(sessions, key=lambda s: s.name):
            if session.group:
                groups.setdefault(session.group, []).append(session)
            else:
                ungrouped.append(session)

        # Add grouped sessions as ExpanderRows
        for group_name in sorted(groups.keys()):
            expander = Adw.ExpanderRow()
            expander.set_title(group_name)
            expander.set_subtitle(f"{len(groups[group_name])} connection(s)")
            expander.set_icon_name("folder-symbolic")
            expander.set_expanded(True)
            expander._group_name = group_name
            expander._group_sessions = groups[group_name]

            # Right-click menu on group folder
            self._attach_group_context_menu(expander, group_name, groups[group_name])

            for session in groups[group_name]:
                row = self._make_session_row(session)
                expander.add_row(row)

            self._session_listbox.append(expander)

        # Add ungrouped sessions
        for session in ungrouped:
            row = self._make_session_row(session)
            self._session_listbox.append(row)

    def show_toast(self, message):
        self._toast_overlay.add_toast(Adw.Toast(title=message))

    # === Broadcast Mode ===

    def set_broadcast_mode(self, active):
        self._broadcast_mode = active
        self._broadcast_btn.set_active(active)
        self._broadcast_bar.set_revealed(active)
        if active:
            self._install_broadcast_key_handler()
        else:
            self._remove_broadcast_key_handler()

    # === Private helpers ===

    def _make_session_row(self, session):
        row = Adw.ActionRow()
        row.set_title(session.name)
        row.set_subtitle(session.connection_string)
        row.set_activatable(True)
        row._session = session

        # Direct activation — works for both top-level and nested rows
        row.connect("activated", self._on_row_activated)

        # Color dot
        if session.color and session.color in TAB_COLORS:
            dot = Gtk.DrawingArea()
            dot.set_size_request(10, 10)
            dot.set_valign(Gtk.Align.CENTER)
            color_hex = TAB_COLORS[session.color]
            dot.set_draw_func(self._draw_color_dot, color_hex)
            row.add_prefix(dot)
        else:
            row.set_icon_name(session.protocol_icon)

        # Connect button
        connect_btn = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER,
                                 tooltip_text="Connect")
        connect_btn.add_css_class("flat")
        connect_btn.connect("clicked", self._on_connect_session, session)
        row.add_suffix(connect_btn)

        # Edit button
        edit_btn = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER,
                              tooltip_text="Edit")
        edit_btn.add_css_class("flat")
        edit_btn.connect("clicked", self._on_edit_session, session)
        row.add_suffix(edit_btn)

        # Delete button
        del_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Delete")
        del_btn.add_css_class("flat")
        del_btn.connect("clicked", self._on_delete_session, session)
        row.add_suffix(del_btn)

        # Right-click context menu on session row
        self._attach_session_context_menu(row, session)

        return row

    def _attach_session_context_menu(self, row, session):
        """Attach a right-click context menu to a session row."""
        menu = Gio.Menu()
        menu.append("Connect", f"session.connect::{session.name}")
        menu.append("Edit", f"session.edit::{session.name}")
        menu.append("Delete", f"session.delete::{session.name}")

        popover = Gtk.PopoverMenu(menu_model=menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)

        # Right-click gesture
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_session_right_click, popover)
        row.add_controller(gesture)

        # Store session ref on popover for action lookup
        popover._session = session

    def _attach_group_context_menu(self, expander, group_name, group_sessions):
        """Attach a right-click context menu to a group folder row."""
        menu = Gio.Menu()
        menu.append("Connect All in Group", f"group.connect-all::{group_name}")
        menu.append("Add Connection to Group", f"group.add-connection::{group_name}")

        popover = Gtk.PopoverMenu(menu_model=menu)
        popover.set_parent(expander)
        popover.set_has_arrow(False)

        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_group_right_click, popover, group_name, group_sessions)
        expander.add_controller(gesture)

    def _on_session_right_click(self, gesture, _n_press, x, y, popover):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)

        # Register temporary actions for this popover
        session = popover._session
        group = Gio.SimpleActionGroup()

        connect_action = Gio.SimpleAction.new("connect", None)
        connect_action.connect("activate", lambda *_: self.open_session_tab(session))
        group.add_action(connect_action)

        edit_action = Gio.SimpleAction.new("edit", None)
        edit_action.connect("activate", lambda *_: self.show_connection_dialog(session=session))
        group.add_action(edit_action)

        delete_action = Gio.SimpleAction.new("delete", None)
        delete_action.connect("activate", lambda *_: self._on_delete_session(None, session))
        group.add_action(delete_action)

        popover.insert_action_group("session", group)
        popover.popup()

    def _on_group_right_click(self, gesture, _n_press, x, y, popover, group_name, group_sessions):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)

        group = Gio.SimpleActionGroup()

        connect_all_action = Gio.SimpleAction.new("connect-all", None)
        connect_all_action.connect("activate", lambda *_: self._connect_group(group_sessions))
        group.add_action(connect_all_action)

        add_action = Gio.SimpleAction.new("add-connection", None)
        add_action.connect("activate", lambda *_: self._add_to_group(group_name))
        group.add_action(add_action)

        popover.insert_action_group("group", group)
        popover.popup()

    def _connect_group(self, sessions):
        """Open tabs for all sessions in a group."""
        for session in sessions:
            self.open_session_tab(session)
        self.show_toast(f"Opened {len(sessions)} session(s)")

    def _add_to_group(self, group_name):
        """Open connection dialog pre-filled with this group name."""
        from tabber.session import Session
        prefilled = Session(group=group_name)
        self.show_connection_dialog(session=prefilled)

    @staticmethod
    def _draw_color_dot(area, cr, width, height, color_hex):
        """Draw a colored circle."""
        rgba = Gdk.RGBA()
        rgba.parse(color_hex)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 3.14159 * 2)
        cr.fill()

    def _apply_zoom(self):
        for i in range(self._tab_view.get_n_pages()):
            page = self._tab_view.get_nth_page(i)
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                tab.set_font_scale(self._font_scale)

    def _get_current_tab(self):
        page = self._tab_view.get_selected_page()
        if page:
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                return tab
        return None

    # --- Broadcast key handling ---

    def _install_broadcast_key_handler(self):
        if not hasattr(self, "_broadcast_controller"):
            self._broadcast_controller = Gtk.EventControllerKey()
            self._broadcast_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self._broadcast_controller.connect("key-pressed", self._on_broadcast_key)
            self.add_controller(self._broadcast_controller)

    def _remove_broadcast_key_handler(self):
        if hasattr(self, "_broadcast_controller"):
            self.remove_controller(self._broadcast_controller)
            del self._broadcast_controller

    def _on_broadcast_key(self, controller, keyval, keycode, state):
        """Forward key presses to all open terminals when in broadcast mode."""
        if not self._broadcast_mode:
            return False

        # Don't intercept modifier-only presses or app shortcuts
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L,
                      Gdk.KEY_Control_R, Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
                      Gdk.KEY_Super_L, Gdk.KEY_Super_R):
            return False

        # Let Ctrl+key shortcuts through (except Ctrl+Shift+C/V which go to terminals)
        ctrl = Gdk.ModifierType.CONTROL_MASK
        if (state & ctrl) and not (state & Gdk.ModifierType.SHIFT_MASK):
            return False

        # Convert keyval to text
        char = Gdk.keyval_to_unicode(keyval)
        if char > 0:
            text = chr(char)
        elif keyval == Gdk.KEY_Return:
            text = "\r"
        elif keyval == Gdk.KEY_Tab:
            text = "\t"
        elif keyval == Gdk.KEY_BackSpace:
            text = "\x7f"
        elif keyval == Gdk.KEY_Escape:
            text = "\x1b"
        else:
            return False

        # Send to all connected terminals in all tabs
        for i in range(self._tab_view.get_n_pages()):
            page = self._tab_view.get_nth_page(i)
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                tab.feed_child_text(text)

        return True

    # --- Signal handlers ---

    def _on_tab_count_changed(self, tab_view, _pspec):
        if tab_view.get_n_pages() == 0:
            self._content_stack.set_visible_child_name("empty")
        else:
            self._content_stack.set_visible_child_name("tabs")

    def _on_tab_selected(self, tab_view, _pspec):
        page = tab_view.get_selected_page()
        if page:
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                tab.terminal.grab_focus()

    def _on_close_page(self, tab_view, page):
        tab = page.get_child()
        if isinstance(tab, TerminalTab) and tab.is_connected():
            dialog = Adw.AlertDialog(
                heading="Close Session?",
                body=f"The session to {tab.session.name} is still active.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("close", "Close")
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_close_confirmed, tab_view, page)
            dialog.present(self)
            return Gdk.EVENT_STOP

        if isinstance(tab, TerminalTab):
            tab.cleanup()
        tab_view.close_page_finish(page, True)
        return Gdk.EVENT_STOP

    def _on_close_confirmed(self, dialog, response, tab_view, page):
        if response == "close":
            tab = page.get_child()
            if isinstance(tab, TerminalTab):
                tab.cleanup()
            tab_view.close_page_finish(page, True)
        else:
            tab_view.close_page_finish(page, False)

    def _on_overview_create_tab(self, overview):
        self.show_connection_dialog()
        return self._tab_view.get_selected_page()

    def _on_add_connection(self, _btn):
        self.show_connection_dialog()

    def _on_session_activated(self, _listbox, row):
        # Fallback for top-level ungrouped rows activated via ListBox signal
        if hasattr(row, "_session"):
            self.open_session_tab(row._session)

    def _on_row_activated(self, row):
        """Direct activation on ActionRow — works for nested rows inside ExpanderRow."""
        if hasattr(row, "_session"):
            self.open_session_tab(row._session)

    def _on_connect_session(self, _btn, session):
        self.open_session_tab(session)

    def _on_session_saved(self, _dialog, session):
        self.refresh_sidebar()

    def _on_edit_session(self, _btn, session):
        self.show_connection_dialog(session=session)

    def _on_delete_session(self, _btn, session):
        dialog = Adw.AlertDialog(
            heading="Delete Connection?",
            body=f'Delete "{session.name}"? This cannot be undone.',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_confirmed, session)
        dialog.present(self)

    def _on_delete_confirmed(self, _dialog, response, session):
        if response == "delete":
            from tabber.session_manager import SessionManager
            manager = SessionManager()
            manager.delete_session(session.name)
            self.refresh_sidebar()
            self.show_toast(f'Deleted "{session.name}"')

    def _on_quick_connect(self, entry):
        text = entry.get_text().strip()
        if not text:
            return
        from tabber.quick_connect import parse_quick_connect
        session = parse_quick_connect(text)
        if session:
            self.open_session_tab(session)
            entry.set_text("")
        else:
            self.show_toast("Invalid connection string")

    def _on_import_sessions(self, *_args):
        from tabber.session_manager import SessionManager
        manager = SessionManager()
        count = manager.import_putty_sessions()
        if count > 0:
            self.refresh_sidebar()
            self.show_toast(f"Imported {count} PuTTY session(s)")
        else:
            self.show_toast("No new PuTTY sessions found to import")

    def _on_search_changed(self, entry):
        text = entry.get_text().lower()

        def filter_func(row):
            if not text:
                return True
            # Handle ExpanderRow (groups)
            if isinstance(row, Adw.ExpanderRow):
                return True  # Always show groups, filter children inside
            title = row.get_title() or ""
            subtitle = row.get_subtitle() or ""
            return text in title.lower() or text in subtitle.lower()

        self._session_listbox.set_filter_func(filter_func)

    def _on_broadcast_toggled(self, btn):
        self.set_broadcast_mode(btn.get_active())

    def _on_broadcast_off(self, _banner):
        self.set_broadcast_mode(False)

    def _on_split_horizontal(self, *_args):
        tab = self._get_current_tab()
        if tab:
            tab.split_horizontal()
            self.show_toast("Split horizontally")

    def _on_split_vertical(self, *_args):
        tab = self._get_current_tab()
        if tab:
            tab.split_vertical()
            self.show_toast("Split vertically")

    def _on_unsplit(self, *_args):
        tab = self._get_current_tab()
        if tab:
            tab.unsplit()
            self.show_toast("Split removed")

    def _on_start_logging(self, *_args):
        tab = self._get_current_tab()
        if tab:
            paths = tab.start_logging()
            if paths:
                self.show_toast(f"Logging to {paths[0]}")
            else:
                self.show_toast("Logging already active")

    def _on_stop_logging(self, *_args):
        tab = self._get_current_tab()
        if tab:
            tab.stop_logging()
            self.show_toast("Logging stopped")

    def _on_sftp_transfer(self, *_args):
        tab = self._get_current_tab()
        if tab and tab.session.protocol == "ssh":
            from tabber.sftp import SftpTransferDialog
            dialog = SftpTransferDialog(tab.session, self)
            dialog.present(self)
        elif tab:
            self.show_toast("SFTP is only available for SSH sessions")
        else:
            self.show_toast("No active session")

    def _on_dark_mode(self, *_args):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self.show_toast("Dark mode enabled")

    def _on_light_mode(self, *_args):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        self.show_toast("Light mode enabled")

    def _on_system_mode(self, *_args):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        self.show_toast("Following system theme")

    def _on_search_terminal(self, *_args):
        self.search_terminal()

    def _on_snippet_activated(self, _panel, text):
        tab = self._get_current_tab()
        if tab and tab.is_connected():
            if self._broadcast_mode:
                # Send to all tabs in broadcast mode
                for i in range(self._tab_view.get_n_pages()):
                    page = self._tab_view.get_nth_page(i)
                    t = page.get_child()
                    if isinstance(t, TerminalTab):
                        t.feed_child_text(text)
            else:
                tab.feed_child_text(text)
        else:
            self.show_toast("No connected session to send snippet to")
