"""Connection create/edit dialog."""

from gi.repository import Adw, GObject, Gtk

from tabber.session import DEFAULT_PORTS, Session
from tabber.session_manager import SessionManager

PROTOCOLS = ["ssh", "telnet", "rlogin", "raw", "serial"]


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
        self.set_content_width(460)
        self.set_content_height(520)

        self._build_ui()
        self._populate_fields()

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        # Header bar with Cancel / Save
        header = Adw.HeaderBar()
        header.set_show_title(True)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        toolbar.add_top_bar(header)

        # Form content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        page = Adw.PreferencesPage()

        # --- Connection group ---
        conn_group = Adw.PreferencesGroup(title="Connection")

        self._name_row = Adw.EntryRow(title="Name")
        conn_group.add(self._name_row)

        # Protocol combo
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

        # --- Authentication group (SSH only) ---
        self._auth_group = Adw.PreferencesGroup(title="Authentication")

        self._key_row = Adw.EntryRow(title="Private Key Path")
        key_btn = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Browse")
        key_btn.add_css_class("flat")
        key_btn.connect("clicked", self._on_browse_key)
        self._key_row.add_suffix(key_btn)
        self._auth_group.add(self._key_row)

        page.add(self._auth_group)

        # --- Serial group ---
        self._serial_group = Adw.PreferencesGroup(title="Serial Port")

        self._serial_line_row = Adw.EntryRow(title="Device (e.g. /dev/ttyUSB0)")
        self._serial_group.add(self._serial_line_row)

        self._serial_config_row = Adw.EntryRow(title="Configuration (e.g. 9600,8,n,1,N)")
        self._serial_group.add(self._serial_config_row)

        page.add(self._serial_group)

        # --- Tabber metadata group ---
        meta_group = Adw.PreferencesGroup(title="Organization")

        self._group_row = Adw.EntryRow(title="Group / Folder")
        meta_group.add(self._group_row)

        self._color_row = Adw.ComboRow(title="Tab Color")
        color_list = Gtk.StringList()
        for c in ["None", "Red", "Orange", "Yellow", "Green", "Blue", "Purple"]:
            color_list.append(c)
        self._color_row.set_model(color_list)
        meta_group.add(self._color_row)

        self._notes_row = Adw.EntryRow(title="Notes")
        meta_group.add(self._notes_row)

        page.add(meta_group)

        scroll.set_child(page)
        toolbar.set_content(scroll)

        # Initial visibility
        self._update_section_visibility()

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

        # Set protocol combo
        try:
            idx = PROTOCOLS.index(s.protocol)
            self._protocol_row.set_selected(idx)
        except ValueError:
            self._protocol_row.set_selected(0)

        # Set color combo
        color_map = {"": 0, "red": 1, "orange": 2, "yellow": 3, "green": 4, "blue": 5, "purple": 6}
        self._color_row.set_selected(color_map.get(s.color, 0))

    def _on_protocol_changed(self, combo, _pspec):
        idx = combo.get_selected()
        protocol = PROTOCOLS[idx]
        default_port = DEFAULT_PORTS.get(protocol, 22)
        self._port_row.set_value(default_port)
        self._update_section_visibility()

    def _update_section_visibility(self):
        idx = self._protocol_row.get_selected()
        protocol = PROTOCOLS[idx]
        self._auth_group.set_visible(protocol == "ssh")
        self._serial_group.set_visible(protocol == "serial")
        self._hostname_row.set_visible(protocol != "serial")
        self._port_row.set_visible(protocol != "serial")
        self._username_row.set_visible(protocol in ("ssh", "telnet", "rlogin"))

    def _on_browse_key(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Private Key")
        dialog.open(self.get_root(), None, self._on_key_file_selected)

    def _on_key_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self._key_row.set_text(file.get_path())
        except Exception:
            pass

    def _on_save(self, _btn):
        name = self._name_row.get_text().strip()
        if not name:
            self._name_row.add_css_class("error")
            return

        idx = self._protocol_row.get_selected()
        protocol = PROTOCOLS[idx]

        if protocol != "serial":
            hostname = self._hostname_row.get_text().strip()
            if not hostname:
                self._hostname_row.add_css_class("error")
                return
        else:
            hostname = ""

        color_idx = self._color_row.get_selected()
        color_names = ["", "red", "orange", "yellow", "green", "blue", "purple"]

        session = Session(
            name=name,
            hostname=hostname,
            port=int(self._port_row.get_value()),
            protocol=protocol,
            username=self._username_row.get_text().strip(),
            identity_file=self._key_row.get_text().strip(),
            group=self._group_row.get_text().strip(),
            color=color_names[color_idx],
            notes=self._notes_row.get_text().strip(),
            serial_line=self._serial_line_row.get_text().strip(),
            serial_config=self._serial_config_row.get_text().strip(),
            last_connected=self._session.last_connected,
        )

        manager = SessionManager()

        # Handle rename
        if self._editing and self._original_name and self._original_name != name:
            manager.delete_session(self._original_name)

        manager.save_session(session)
        self.emit("session-saved", session)
        self.close()
