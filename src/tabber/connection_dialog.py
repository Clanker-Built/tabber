"""Connection create/edit dialog with PuTTY-style tabbed sections."""

from gi.repository import Adw, GObject, Gtk

from tabber.session import DEFAULT_PORTS, Session
from tabber.session_manager import SessionManager

PROTOCOLS = ["ssh", "telnet", "rlogin", "raw", "serial"]
COLOR_NAMES = ["", "red", "orange", "yellow", "green", "blue", "purple"]
COLOR_LABELS = ["None", "Red", "Orange", "Yellow", "Green", "Blue", "Purple"]
TUNNEL_TYPES = [("L", "Local"), ("R", "Remote"), ("D", "Dynamic (SOCKS)")]


class ConnectionDialog(Adw.Dialog):
    __gsignals__ = {
        "session-saved": (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self, session=None, transient_for=None, **kwargs):
        super().__init__(**kwargs)
        self._editing = session is not None
        self._original_name = session.name if session else None
        self._session = session.copy() if session else Session()

        self.set_title("Edit Connection" if self._editing else "New Connection")
        self.set_content_width(620)
        self.set_content_height(640)

        self._tunnel_rows = []
        self._build_ui()
        self._populate_fields()

    # === UI construction ===

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        # Header is dedicated to the stack switcher so tab labels aren't squeezed.
        # Gtk.StackSwitcher sizes each tab to its content (asymmetric), unlike
        # Adw.ViewSwitcher which forces equal widths.
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)

        self._view_stack = Gtk.Stack()
        self._view_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=self._view_stack)
        header.set_title_widget(switcher)
        toolbar.add_top_bar(header)

        # Cancel / Save live in a bottom action bar
        bottom_bar = Gtk.ActionBar()
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        bottom_bar.pack_start(cancel_btn)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        bottom_bar.pack_end(save_btn)
        toolbar.add_bottom_bar(bottom_bar)

        # Labels only: Gtk.StackSwitcher collapses to icon-only when icons
        # are present, which defeats the whole point of asymmetric widths.
        self._view_stack.add_titled(self._build_basic_page(), "basic", "Quick Connect")
        self._ssh_page_widget = self._build_ssh_page()
        self._view_stack.add_titled(self._ssh_page_widget, "ssh", "SSH")
        self._tunnels_page_widget = self._build_tunnels_page()
        self._view_stack.add_titled(self._tunnels_page_widget, "tunnels", "Tunnels")
        self._view_stack.add_titled(self._build_proxy_page(), "proxy", "Proxy")
        self._view_stack.add_titled(self._build_terminal_page(), "terminal", "Terminal")

        toolbar.set_content(self._view_stack)

    def _scrolled_page(self, page):
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(page)
        return scroll

    def _build_basic_page(self):
        page = Adw.PreferencesPage()

        conn_group = Adw.PreferencesGroup(title="Connection")
        self._name_row = Adw.EntryRow(title="Name")
        conn_group.add(self._name_row)

        self._protocol_row = Adw.ComboRow(title="Protocol")
        protocol_list = Gtk.StringList()
        for p in PROTOCOLS:
            protocol_list.append(p.upper())
        self._protocol_row.set_model(protocol_list)
        self._protocol_row.connect("notify::selected", self._on_protocol_changed)
        conn_group.add(self._protocol_row)

        self._hostname_row = Adw.EntryRow(title="Hostname")
        conn_group.add(self._hostname_row)

        self._port_row = Adw.SpinRow.new_with_range(0, 65535, 1)
        self._port_row.set_title("Port")
        self._port_row.set_value(22)
        conn_group.add(self._port_row)

        self._username_row = Adw.EntryRow(title="Username")
        conn_group.add(self._username_row)

        page.add(conn_group)

        # SSH key on the basic page (most common need)
        self._auth_group = Adw.PreferencesGroup(title="Authentication")
        self._key_row = Adw.EntryRow(title="Private Key Path")
        key_btn = Gtk.Button(icon_name="document-open-symbolic",
                             valign=Gtk.Align.CENTER, tooltip_text="Browse")
        key_btn.add_css_class("flat")
        key_btn.connect("clicked", lambda _b: self._browse_into(self._key_row,
                                                                "Select Private Key"))
        self._key_row.add_suffix(key_btn)
        self._auth_group.add(self._key_row)
        page.add(self._auth_group)

        # Serial group lives on the basic page (only one place it's relevant)
        self._serial_group = Adw.PreferencesGroup(title="Serial Port")
        self._serial_line_row = Adw.EntryRow(title="Device (e.g. /dev/ttyUSB0)")
        self._serial_group.add(self._serial_line_row)
        self._serial_config_row = Adw.EntryRow(title="Configuration (e.g. 9600,8,n,1,N)")
        self._serial_group.add(self._serial_config_row)
        page.add(self._serial_group)

        return self._scrolled_page(page)

    def _build_ssh_page(self):
        page = Adw.PreferencesPage()

        feat_group = Adw.PreferencesGroup(title="Protocol")
        self._compression_row = Adw.SwitchRow(title="Enable compression",
                                              subtitle="plink -C")
        feat_group.add(self._compression_row)
        self._x11_row = Adw.SwitchRow(title="Enable X11 forwarding",
                                      subtitle="plink -X")
        feat_group.add(self._x11_row)
        self._no_pty_row = Adw.SwitchRow(title="Don't allocate a pseudo-terminal",
                                         subtitle="plink -T")
        feat_group.add(self._no_pty_row)
        self._no_shell_row = Adw.SwitchRow(title="Don't run a shell or command",
                                           subtitle="plink -N (port forward only)")
        feat_group.add(self._no_shell_row)
        page.add(feat_group)

        auth_group = Adw.PreferencesGroup(title="Authentication")
        self._use_agent_row = Adw.SwitchRow(title="Use Pageant / SSH agent",
                                            subtitle="plink -agent / -noagent")
        auth_group.add(self._use_agent_row)
        self._agent_fwd_row = Adw.SwitchRow(title="Allow agent forwarding",
                                            subtitle="plink -A")
        auth_group.add(self._agent_fwd_row)

        self._cert_row = Adw.EntryRow(title="Certificate file")
        cert_btn = Gtk.Button(icon_name="document-open-symbolic",
                              valign=Gtk.Align.CENTER, tooltip_text="Browse")
        cert_btn.add_css_class("flat")
        cert_btn.connect("clicked", lambda _b: self._browse_into(self._cert_row,
                                                                 "Select Certificate"))
        self._cert_row.add_suffix(cert_btn)
        auth_group.add(self._cert_row)
        page.add(auth_group)

        return self._scrolled_page(page)

    def _build_tunnels_page(self):
        page = Adw.PreferencesPage()

        self._tunnels_group = Adw.PreferencesGroup(
            title="Port Forwards",
            description=("Local: forward a local port to a remote target.  "
                         "Remote: forward a remote port back to a local target.  "
                         "Dynamic: SOCKS proxy on a local port."),
        )

        add_btn = Gtk.Button(icon_name="list-add-symbolic",
                             tooltip_text="Add forward")
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", lambda _b: self._add_tunnel_row({}))
        self._tunnels_group.set_header_suffix(add_btn)

        self._tunnels_listbox = Gtk.ListBox()
        self._tunnels_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._tunnels_listbox.add_css_class("boxed-list")

        self._tunnels_empty = Adw.ActionRow(
            title="No port forwards",
            subtitle="Click + to add one",
        )
        self._tunnels_listbox.append(self._tunnels_empty)
        self._tunnels_group.add(self._tunnels_listbox)
        page.add(self._tunnels_group)

        return self._scrolled_page(page)

    def _build_proxy_page(self):
        page = Adw.PreferencesPage()

        proxy_group = Adw.PreferencesGroup(title="Jump Host / Proxy")
        self._jump_row = Adw.EntryRow(title="Jump host ([user@]host[:port])")
        proxy_group.add(self._jump_row)
        self._proxy_cmd_row = Adw.EntryRow(title="Proxy command")
        proxy_group.add(self._proxy_cmd_row)
        page.add(proxy_group)

        net_group = Adw.PreferencesGroup(title="Network")
        self._ip_row = Adw.ComboRow(title="IP version")
        ip_list = Gtk.StringList()
        for v in ["Auto", "IPv4 only", "IPv6 only"]:
            ip_list.append(v)
        self._ip_row.set_model(ip_list)
        net_group.add(self._ip_row)

        self._loghost_row = Adw.EntryRow(title="Logical host name (-loghost)")
        net_group.add(self._loghost_row)
        page.add(net_group)

        return self._scrolled_page(page)

    def _build_terminal_page(self):
        page = Adw.PreferencesPage()

        org_group = Adw.PreferencesGroup(title="Organization")
        self._group_row = Adw.EntryRow(title="Group / Folder")
        org_group.add(self._group_row)
        self._color_row = Adw.ComboRow(title="Tab Color")
        color_list = Gtk.StringList()
        for c in COLOR_LABELS:
            color_list.append(c)
        self._color_row.set_model(color_list)
        org_group.add(self._color_row)
        self._notes_row = Adw.EntryRow(title="Notes")
        org_group.add(self._notes_row)
        page.add(org_group)

        return self._scrolled_page(page)

    # === Tunnel rows ===

    def _add_tunnel_row(self, data):
        if self._tunnels_empty.get_parent() is self._tunnels_listbox:
            self._tunnels_listbox.remove(self._tunnels_empty)

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=6, margin_top=6, margin_bottom=6,
                          margin_start=6, margin_end=6)

        type_combo = Gtk.DropDown.new_from_strings([t[1] for t in TUNNEL_TYPES])
        type_idx = next((i for i, t in enumerate(TUNNEL_TYPES)
                         if t[0] == data.get("type", "L")), 0)
        type_combo.set_selected(type_idx)
        type_combo.set_size_request(140, -1)
        row_box.append(type_combo)

        listen_entry = Gtk.Entry(placeholder_text="Listen port",
                                 text=data.get("listen", ""), hexpand=True)
        row_box.append(listen_entry)

        target_entry = Gtk.Entry(placeholder_text="host:port",
                                 text=data.get("target", ""), hexpand=True)
        row_box.append(target_entry)

        delete_btn = Gtk.Button(icon_name="user-trash-symbolic",
                                valign=Gtk.Align.CENTER)
        delete_btn.add_css_class("flat")
        row_box.append(delete_btn)

        row = Gtk.ListBoxRow(child=row_box, activatable=False)
        self._tunnels_listbox.append(row)

        entry = {
            "row": row,
            "type": type_combo,
            "listen": listen_entry,
            "target": target_entry,
        }
        self._tunnel_rows.append(entry)

        # Dynamic tunnels don't need a target
        def update_target_sensitivity(*_):
            is_dynamic = TUNNEL_TYPES[type_combo.get_selected()][0] == "D"
            target_entry.set_sensitive(not is_dynamic)
            if is_dynamic:
                target_entry.set_text("")
        type_combo.connect("notify::selected", update_target_sensitivity)
        update_target_sensitivity()

        delete_btn.connect("clicked", lambda _b: self._remove_tunnel_row(entry))

    def _remove_tunnel_row(self, entry):
        self._tunnels_listbox.remove(entry["row"])
        self._tunnel_rows.remove(entry)
        if not self._tunnel_rows:
            self._tunnels_listbox.append(self._tunnels_empty)

    def _collect_tunnels(self):
        tunnels = []
        for entry in self._tunnel_rows:
            ttype = TUNNEL_TYPES[entry["type"].get_selected()][0]
            listen = entry["listen"].get_text().strip()
            target = entry["target"].get_text().strip()
            if not listen:
                continue
            if ttype != "D" and not target:
                continue
            tunnels.append({"type": ttype, "listen": listen, "target": target})
        return tunnels

    # === Populate / save ===

    def _populate_fields(self):
        s = self._session
        self._name_row.set_text(s.name)
        self._hostname_row.set_text(s.hostname)
        self._port_row.set_value(s.port or DEFAULT_PORTS.get(s.protocol, 22))
        self._username_row.set_text(s.username)
        self._key_row.set_text(s.identity_file)
        self._serial_line_row.set_text(s.serial_line)
        self._serial_config_row.set_text(s.serial_config)
        self._group_row.set_text(s.group)
        self._notes_row.set_text(s.notes)

        try:
            self._protocol_row.set_selected(PROTOCOLS.index(s.protocol))
        except ValueError:
            self._protocol_row.set_selected(0)

        try:
            self._color_row.set_selected(COLOR_NAMES.index(s.color))
        except ValueError:
            self._color_row.set_selected(0)

        # SSH tab
        self._compression_row.set_active(s.compression)
        self._x11_row.set_active(s.x11_forward)
        self._no_pty_row.set_active(s.no_pty)
        self._no_shell_row.set_active(s.no_shell)
        self._use_agent_row.set_active(s.use_agent)
        self._agent_fwd_row.set_active(s.agent_forward)
        self._cert_row.set_text(s.cert_file)

        # Tunnels
        for t in s.tunnels:
            self._add_tunnel_row(t)

        # Proxy / network
        self._jump_row.set_text(s.jump_host)
        self._proxy_cmd_row.set_text(s.proxy_command)
        ip_idx = {"": 0, "4": 1, "6": 2}.get(s.ip_version, 0)
        self._ip_row.set_selected(ip_idx)
        self._loghost_row.set_text(s.logical_host)

        self._update_section_visibility()

    def _on_protocol_changed(self, combo, _pspec):
        protocol = PROTOCOLS[combo.get_selected()]
        self._port_row.set_value(DEFAULT_PORTS.get(protocol, 22))
        self._update_section_visibility()

    def _update_section_visibility(self):
        protocol = PROTOCOLS[self._protocol_row.get_selected()]
        is_serial = protocol == "serial"
        is_ssh = protocol == "ssh"

        self._serial_group.set_visible(is_serial)
        self._auth_group.set_visible(is_ssh)
        self._hostname_row.set_visible(not is_serial)
        self._port_row.set_visible(not is_serial)
        self._username_row.set_visible(protocol in ("ssh", "telnet", "rlogin"))

        # SSH/Tunnels pages only meaningful for SSH
        ssh_page = self._view_stack.get_page(self._ssh_page_widget)
        tunnels_page = self._view_stack.get_page(self._tunnels_page_widget)
        if ssh_page:
            ssh_page.set_visible(is_ssh)
        if tunnels_page:
            tunnels_page.set_visible(is_ssh)

    def _browse_into(self, entry_row, title):
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        dialog.open(self.get_root(), None,
                    lambda d, r: self._on_file_selected(d, r, entry_row))

    def _on_file_selected(self, dialog, result, entry_row):
        try:
            file = dialog.open_finish(result)
            if file:
                entry_row.set_text(file.get_path())
        except Exception:
            pass

    def _on_save(self, _btn):
        name = self._name_row.get_text().strip()
        if not name:
            self._name_row.add_css_class("error")
            self._view_stack.set_visible_child_name("basic")
            return

        protocol = PROTOCOLS[self._protocol_row.get_selected()]

        if protocol != "serial":
            hostname = self._hostname_row.get_text().strip()
            if not hostname:
                self._hostname_row.add_css_class("error")
                self._view_stack.set_visible_child_name("basic")
                return
        else:
            hostname = ""

        ip_version = ["", "4", "6"][self._ip_row.get_selected()]

        session = Session(
            name=name,
            hostname=hostname,
            port=int(self._port_row.get_value()),
            protocol=protocol,
            username=self._username_row.get_text().strip(),
            identity_file=self._key_row.get_text().strip(),
            compression=self._compression_row.get_active(),
            use_agent=self._use_agent_row.get_active(),
            agent_forward=self._agent_fwd_row.get_active(),
            cert_file=self._cert_row.get_text().strip(),
            no_shell=self._no_shell_row.get_active(),
            no_pty=self._no_pty_row.get_active(),
            x11_forward=self._x11_row.get_active(),
            tunnels=self._collect_tunnels(),
            jump_host=self._jump_row.get_text().strip(),
            proxy_command=self._proxy_cmd_row.get_text().strip(),
            ip_version=ip_version,
            logical_host=self._loghost_row.get_text().strip(),
            group=self._group_row.get_text().strip(),
            color=COLOR_NAMES[self._color_row.get_selected()],
            notes=self._notes_row.get_text().strip(),
            serial_line=self._serial_line_row.get_text().strip(),
            serial_config=self._serial_config_row.get_text().strip(),
            last_connected=self._session.last_connected,
        )

        manager = SessionManager()
        if self._editing and self._original_name and self._original_name != name:
            manager.delete_session(self._original_name)
        manager.save_session(session)
        self.emit("session-saved", session)
        self.close()
