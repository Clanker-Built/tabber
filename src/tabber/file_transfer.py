"""Dual-pane SFTP file browser window."""

import os
import stat
from datetime import datetime
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from tabber.psftp_backend import PsftpBackend


def _format_size(n):
    if n < 1024:
        return f"{n} B"
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PiB"


def _format_local_mtime(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


class _Pane(Gtk.Box):
    """Common pane chrome (path bar + list area + action bar). Subclasses provide
    the actual file listing and upload/download actions."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

    def _build_path_bar(self, up_cb, home_cb, activate_cb, refresh_cb):
        path_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            margin_start=6, margin_end=6, margin_top=6, margin_bottom=6,
        )
        up_btn = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Up")
        up_btn.connect("clicked", lambda _b: up_cb())
        path_bar.append(up_btn)

        home_btn = Gtk.Button(icon_name="go-home-symbolic", tooltip_text="Home")
        home_btn.connect("clicked", lambda _b: home_cb())
        path_bar.append(home_btn)

        self._path_entry = Gtk.Entry(hexpand=True)
        self._path_entry.connect("activate", lambda e: activate_cb(e.get_text()))
        path_bar.append(self._path_entry)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_btn.connect("clicked", lambda _b: refresh_cb())
        path_bar.append(refresh_btn)

        return path_bar

    def _build_header_row(self):
        """Column header strip above the list. Labels align with row columns
        via the same size_request values."""
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=14, margin_end=14, margin_top=2, margin_bottom=4,
        )
        # Invisible spacer matching the row icon (~16px + spacing).
        spacer = Gtk.Box()
        spacer.set_size_request(16, -1)
        box.append(spacer)

        name_lbl = Gtk.Label(label="Name", xalign=0, hexpand=True)
        name_lbl.add_css_class("heading")
        name_lbl.add_css_class("caption")
        box.append(name_lbl)

        size_lbl = Gtk.Label(label="Size", xalign=1)
        size_lbl.set_size_request(80, -1)
        size_lbl.add_css_class("heading")
        size_lbl.add_css_class("caption")
        box.append(size_lbl)

        mtime_lbl = Gtk.Label(label="Modified", xalign=1)
        mtime_lbl.set_size_request(140, -1)
        mtime_lbl.add_css_class("heading")
        mtime_lbl.add_css_class("caption")
        box.append(mtime_lbl)
        return box

    def _build_listbox(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        # Activation requires triple-click (see _attach_triple_click); the
        # row-activated signal stays connected for keyboard Enter only, so
        # single-click selection never accidentally transfers a file.
        listbox.set_activate_on_single_click(False)
        listbox.add_css_class("boxed-list")
        listbox.set_margin_start(6)
        listbox.set_margin_end(6)
        listbox.set_margin_top(2)
        listbox.set_margin_bottom(2)
        scroll.set_child(listbox)
        return scroll, listbox

    def _attach_click_gestures(self, listbox, navigate_cb, transfer_cb):
        """Click semantics:
          1 click  — select (Gtk default).
          2 clicks — navigate into a folder (files: no-op). Deferred by
                     ~250ms so a third click can upgrade to a transfer.
          3 clicks — transfer the row (file or folder) to the other pane.
        Called callbacks receive the row directly."""
        gesture = Gtk.GestureClick(button=1)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

        state = {"pending": None}

        def _cancel_pending():
            if state["pending"] is not None:
                GLib.source_remove(state["pending"])
                state["pending"] = None

        def _fire_navigate(row):
            state["pending"] = None
            navigate_cb(row)
            return False

        def _on_pressed(_g, n_press, x, y):
            row = listbox.get_row_at_y(int(y))
            if row is None:
                _cancel_pending()
                return
            if n_press == 2:
                _cancel_pending()
                # Claim so GtkListBox's built-in activation does not fire.
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                state["pending"] = GLib.timeout_add(250, _fire_navigate, row)
            elif n_press >= 3:
                _cancel_pending()
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                transfer_cb(row)
        gesture.connect("pressed", _on_pressed)
        listbox.add_controller(gesture)

    def _make_row(self, name, is_dir, is_link, size, mtime):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=8, margin_end=8, margin_top=4, margin_bottom=4,
        )
        if is_dir:
            icon_name = "folder-symbolic"
        elif is_link:
            icon_name = "emblem-symbolic-link"
        else:
            icon_name = "text-x-generic-symbolic"
        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.append(icon)

        name_label = Gtk.Label(
            label=name, xalign=0, hexpand=True,
            ellipsize=Pango.EllipsizeMode.END,
        )
        box.append(name_label)

        size_label = Gtk.Label(
            label=("" if is_dir else _format_size(size)),
            xalign=1,
        )
        size_label.set_size_request(80, -1)
        size_label.add_css_class("dim-label")
        box.append(size_label)

        mtime_label = Gtk.Label(label=mtime, xalign=1)
        mtime_label.set_size_request(140, -1)
        mtime_label.add_css_class("dim-label")
        mtime_label.add_css_class("caption")
        box.append(mtime_label)

        row.set_child(box)
        return row

    def _clear_listbox(self, listbox):
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)


class LocalPane(_Pane):
    """Browse the local filesystem."""

    __gsignals__ = {
        "upload-requested": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "status": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._cwd = Path.home()
        self._show_hidden = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        path_bar = self._build_path_bar(
            up_cb=self.navigate_up,
            home_cb=lambda: self.navigate(str(Path.home())),
            activate_cb=self.navigate,
            refresh_cb=self.refresh,
        )
        self.append(path_bar)

        self.append(self._build_header_row())

        scroll, self._listbox = self._build_listbox()
        # Keyboard Enter still fires row-activated and navigates folders.
        self._listbox.connect("row-activated", self._on_row_activated_kbd)
        self._attach_click_gestures(
            self._listbox,
            navigate_cb=self._on_navigate_row,
            transfer_cb=self._on_transfer_row,
        )
        self._attach_context_menu()
        self.append(scroll)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
            margin_start=6, margin_end=6, margin_top=4, margin_bottom=6,
        )
        upload_btn = Gtk.Button(label="Upload \u2192")
        upload_btn.add_css_class("suggested-action")
        upload_btn.connect("clicked", self._on_upload)
        actions.append(upload_btn)

        spacer = Gtk.Box(hexpand=True)
        actions.append(spacer)

        hidden_toggle = Gtk.ToggleButton(
            icon_name="view-reveal-symbolic", tooltip_text="Show hidden files",
        )
        hidden_toggle.connect("toggled", self._on_toggle_hidden)
        actions.append(hidden_toggle)

        self.append(actions)

    def _attach_context_menu(self):
        menu = Gio.Menu()
        menu.append("Upload to Remote", "local.upload")
        menu.append("Refresh", "local.refresh")
        self._popover = Gtk.PopoverMenu.new_from_model(menu)
        self._popover.set_parent(self._listbox)
        self._popover.set_has_arrow(False)

        group = Gio.SimpleActionGroup()
        upload_action = Gio.SimpleAction.new("upload", None)
        upload_action.connect("activate", lambda *_: self._on_upload(None))
        group.add_action(upload_action)
        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect("activate", lambda *_: self.refresh())
        group.add_action(refresh_action)
        self._listbox.insert_action_group("local", group)

        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_right_click)
        self._listbox.add_controller(gesture)

    def _on_right_click(self, _gesture, _n_press, x, y):
        row = self._listbox.get_row_at_y(int(y))
        if row and row not in self._listbox.get_selected_rows():
            self._listbox.unselect_all()
            self._listbox.select_row(row)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._popover.set_pointing_to(rect)
        self._popover.popup()

    def refresh(self):
        self._path_entry.set_text(str(self._cwd))
        self._clear_listbox(self._listbox)

        try:
            entries = list(os.scandir(self._cwd))
        except PermissionError:
            self.emit("status", f"Permission denied: {self._cwd}")
            return
        except (FileNotFoundError, NotADirectoryError):
            self.emit("status", f"Not a directory: {self._cwd}")
            return

        def sort_key(e):
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            return (0 if is_dir else 1, e.name.lower())

        entries.sort(key=sort_key)
        for entry in entries:
            if not self._show_hidden and entry.name.startswith("."):
                continue
            try:
                st = entry.stat(follow_symlinks=False)
                is_dir = stat.S_ISDIR(st.st_mode)
                is_link = stat.S_ISLNK(st.st_mode)
                size = st.st_size
                mtime = _format_local_mtime(st.st_mtime)
            except OSError:
                continue
            row = self._make_row(entry.name, is_dir, is_link, size, mtime)
            row._full_path = entry.path
            row._is_dir = is_dir
            row._name = entry.name
            self._listbox.append(row)

    def navigate(self, path):
        p = Path(path).expanduser()
        try:
            if not p.is_dir():
                self.emit("status", f"Not a directory: {path}")
                return
            self._cwd = p.resolve()
        except OSError as e:
            self.emit("status", f"Cannot open: {e}")
            return
        self.refresh()

    def navigate_up(self):
        parent = self._cwd.parent
        if parent != self._cwd:
            self._cwd = parent
            self.refresh()

    def get_cwd(self):
        return str(self._cwd)

    def get_selected_paths(self):
        return [row._full_path for row in self._listbox.get_selected_rows()]

    def _on_navigate_row(self, row):
        # Double-click folder navigates. Double-click file is a no-op —
        # single click already selected it; use triple-click to transfer.
        if row._is_dir:
            self.navigate(row._full_path)

    def _on_transfer_row(self, row):
        # Triple-click transfers file OR folder (recursive handled by backend).
        self.emit("upload-requested", [row._full_path])

    def _on_row_activated_kbd(self, _lb, row):
        self._on_navigate_row(row)

    def _on_upload(self, _btn):
        paths = self.get_selected_paths()
        if not paths:
            self.emit("status", "No local files selected")
            return
        self.emit("upload-requested", paths)

    def _on_toggle_hidden(self, btn):
        self._show_hidden = btn.get_active()
        self.refresh()


class RemotePane(_Pane):
    """Browse the remote filesystem via a PsftpBackend."""

    __gsignals__ = {
        "download-requested": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "status": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "operation-started": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "operation-progress": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "operation-finished": (GObject.SignalFlags.RUN_FIRST, None, (bool, str)),
    }

    def __init__(self, backend):
        super().__init__()
        self._backend = backend
        self._cwd = "/"
        self._home_path = "/"
        self._show_hidden = False
        self._build_ui()

    def _build_ui(self):
        path_bar = self._build_path_bar(
            up_cb=self.navigate_up,
            home_cb=self._go_home,
            activate_cb=self.navigate,
            refresh_cb=self.refresh,
        )
        self.append(path_bar)

        self.append(self._build_header_row())

        # Stack: loading / list / error
        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)

        loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        loading.set_valign(Gtk.Align.CENTER)
        loading.set_halign(Gtk.Align.CENTER)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(32, 32)
        loading.append(self._spinner)
        self._stack.add_named(loading, "loading")

        scroll, self._listbox = self._build_listbox()
        self._listbox.connect("row-activated", self._on_row_activated_kbd)
        self._attach_click_gestures(
            self._listbox,
            navigate_cb=self._on_navigate_row,
            transfer_cb=self._on_transfer_row,
        )
        self._attach_context_menu()
        self._stack.add_named(scroll, "list")

        error_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
            margin_start=24, margin_end=24,
        )
        self._error_label = Gtk.Label(wrap=True, max_width_chars=60)
        self._error_label.add_css_class("dim-label")
        error_box.append(self._error_label)
        self._stack.add_named(error_box, "error")

        self._stack.set_visible_child_name("loading")
        self.append(self._stack)

        # Actions
        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
            margin_start=6, margin_end=6, margin_top=4, margin_bottom=6,
        )
        download_btn = Gtk.Button(label="\u2190 Download")
        download_btn.add_css_class("suggested-action")
        download_btn.connect("clicked", self._on_download)
        actions.append(download_btn)

        mkdir_btn = Gtk.Button(icon_name="folder-new-symbolic", tooltip_text="New Folder")
        mkdir_btn.connect("clicked", self._on_mkdir)
        actions.append(mkdir_btn)

        delete_btn = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete Selected")
        delete_btn.connect("clicked", self._on_delete)
        actions.append(delete_btn)

        rename_btn = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Rename")
        rename_btn.connect("clicked", self._on_rename)
        actions.append(rename_btn)

        spacer = Gtk.Box(hexpand=True)
        actions.append(spacer)

        hidden_toggle = Gtk.ToggleButton(
            icon_name="view-reveal-symbolic", tooltip_text="Show hidden files",
        )
        hidden_toggle.connect("toggled", self._on_toggle_hidden)
        actions.append(hidden_toggle)

        self.append(actions)

    def _attach_context_menu(self):
        menu = Gio.Menu()
        menu.append("Download to Local", "remote.download")
        menu.append("Rename\u2026", "remote.rename")
        menu.append("Delete\u2026", "remote.delete")
        sep = Gio.Menu()
        sep.append("New Folder\u2026", "remote.mkdir")
        sep.append("Refresh", "remote.refresh")
        menu.append_section(None, sep)

        self._popover = Gtk.PopoverMenu.new_from_model(menu)
        self._popover.set_parent(self._listbox)
        self._popover.set_has_arrow(False)

        group = Gio.SimpleActionGroup()
        for name, cb in [
            ("download", lambda *_: self._on_download(None)),
            ("rename", lambda *_: self._on_rename(None)),
            ("delete", lambda *_: self._on_delete(None)),
            ("mkdir", lambda *_: self._on_mkdir(None)),
            ("refresh", lambda *_: self.refresh()),
        ]:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            group.add_action(act)
        self._listbox.insert_action_group("remote", group)

        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_right_click)
        self._listbox.add_controller(gesture)

    def _on_right_click(self, _gesture, _n_press, x, y):
        row = self._listbox.get_row_at_y(int(y))
        if row and row not in self._listbox.get_selected_rows():
            self._listbox.unselect_all()
            self._listbox.select_row(row)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._popover.set_pointing_to(rect)
        self._popover.popup()

    def set_initial_cwd(self, path):
        self._cwd = path
        self._home_path = path
        self.refresh()

    def refresh(self):
        self._path_entry.set_text(self._cwd)
        self._spinner.start()
        self._stack.set_visible_child_name("loading")
        self._backend.list_dir(self._cwd, self._on_listed)

    def _on_listed(self, entries, error):
        self._spinner.stop()
        if error is not None:
            self._error_label.set_label(f"Error: {error}")
            self._stack.set_visible_child_name("error")
            return

        self._clear_listbox(self._listbox)
        entries.sort(key=lambda e: (0 if e.is_dir else 1, e.name.lower()))
        for entry in entries:
            if not self._show_hidden and entry.name.startswith("."):
                continue
            row = self._make_row(entry.name, entry.is_dir, entry.is_link, entry.size, entry.mtime)
            row._entry = entry
            self._listbox.append(row)
        self._stack.set_visible_child_name("list")

    def navigate(self, path):
        if not path.startswith("/"):
            path = self._join(self._cwd, path)
        self._cwd = self._normalize(path)
        self.refresh()

    def navigate_up(self):
        self._cwd = self._normalize(self._cwd + "/..")
        self.refresh()

    def _go_home(self):
        self._cwd = self._home_path
        self.refresh()

    def get_cwd(self):
        return self._cwd

    def get_selected_entries(self):
        return [row._entry for row in self._listbox.get_selected_rows()]

    def _on_navigate_row(self, row):
        entry = row._entry
        if entry.is_dir or entry.is_link:
            self.navigate(self._join(self._cwd, entry.name))

    def _on_transfer_row(self, row):
        self.emit("download-requested", [row._entry])

    def _on_row_activated_kbd(self, _lb, row):
        self._on_navigate_row(row)

    def _on_download(self, _btn):
        entries = self.get_selected_entries()
        if not entries:
            self.emit("status", "No remote files selected")
            return
        self.emit("download-requested", entries)

    def _on_mkdir(self, _btn):
        dialog = Adw.AlertDialog(heading="New Folder", body="Folder name:")
        entry = Gtk.Entry()
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")

        def _resp(_d, response):
            if response == "create":
                name = entry.get_text().strip()
                if name:
                    path = self._join(self._cwd, name)
                    self._backend.make_dir(path, self._after_write_op)

        dialog.connect("response", _resp)
        dialog.present(self.get_root())

    def _on_delete(self, _btn):
        entries = self.get_selected_entries()
        if not entries:
            return
        preview = ", ".join(e.name for e in entries[:3])
        if len(entries) > 3:
            preview += f" and {len(entries) - 3} more"
        dialog = Adw.AlertDialog(
            heading="Delete?",
            body=f"Delete {preview}? This cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def _resp(_d, response):
            if response == "delete":
                total = len(entries)
                label = f"Deleting {total} item(s)\u2026"
                self.emit("operation-started", label)
                self._delete_entries(entries, 0, total, fail_count=0)

        dialog.connect("response", _resp)
        dialog.present(self.get_root())

    def _delete_entries(self, entries, idx, total, fail_count):
        if idx >= len(entries):
            if fail_count == 0:
                self.emit("operation-finished", True, f"Deleted {total} item(s)")
            else:
                self.emit("operation-finished", False,
                          f"Deleted {total - fail_count} of {total}; {fail_count} failed")
            self.refresh()
            return
        entry = entries[idx]
        path = self._join(self._cwd, entry.name)
        op = self._backend.remove_dir if entry.is_dir else self._backend.delete_file
        kind = "folder" if entry.is_dir else "file"
        self.emit("operation-progress",
                  f"Deleting {kind} {entry.name} ({idx + 1}/{total})")

        def _done(ok, err):
            next_fail = fail_count if ok else fail_count + 1
            if not ok:
                self.emit("status", f"Delete failed on {entry.name}: {err}")
            self._delete_entries(entries, idx + 1, total, next_fail)
        op(path, _done)

    def _on_rename(self, _btn):
        entries = self.get_selected_entries()
        if len(entries) != 1:
            self.emit("status", "Select exactly one item to rename")
            return
        entry = entries[0]
        dialog = Adw.AlertDialog(heading="Rename", body=f"New name for {entry.name}:")
        name_entry = Gtk.Entry(text=entry.name)
        dialog.set_extra_child(name_entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")

        def _resp(_d, response):
            if response == "rename":
                new_name = name_entry.get_text().strip()
                if new_name and new_name != entry.name:
                    src = self._join(self._cwd, entry.name)
                    dst = self._join(self._cwd, new_name)
                    self._backend.rename(src, dst, self._after_write_op)

        dialog.connect("response", _resp)
        dialog.present(self.get_root())

    def _after_write_op(self, ok, err):
        if not ok:
            self.emit("status", f"Failed: {err}")
        self.refresh()

    def _on_toggle_hidden(self, btn):
        self._show_hidden = btn.get_active()
        self.refresh()

    @staticmethod
    def _join(a, b):
        if a.endswith("/"):
            return a + b
        return a + "/" + b

    @staticmethod
    def _normalize(path):
        parts = []
        for p in path.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)


class FileTransferWindow(Adw.Window):
    """Top-level dual-pane file transfer window for a single SSH session."""

    def __init__(self, session, application, **kwargs):
        super().__init__(
            default_width=1050,
            default_height=650,
            title=f"File Transfer \u2014 {session.name or session.hostname}",
            **kwargs,
        )
        self.set_application(application)
        self._session = session
        self._password = None  # in-memory for window lifetime only
        self._backend = None
        self._build_ui()
        self.connect("close-request", self._on_close_request)
        # If no key auth, prompt for password up front. Otherwise try key first.
        if session.identity_file:
            self._start_backend()
        else:
            GLib.idle_add(self._prompt_password, "Password required", False)

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        subtitle = Gtk.Label(
            label=f"{self._session.username}@{self._session.hostname}" if self._session.username
            else self._session.hostname
        )
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        t = Gtk.Label(label="File Transfer")
        t.add_css_class("heading")
        title_box.append(t)
        title_box.append(subtitle)
        header.set_title_widget(title_box)
        toolbar.add_top_bar(header)

        self._toast_overlay = Adw.ToastOverlay()
        toolbar.set_content(self._toast_overlay)

        # Bottom status bar: progress bar + status label. Pulses while a
        # transfer is in flight, shows explicit Done / Failed afterwards.
        self._status_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=10, margin_end=10, margin_top=4, margin_bottom=4,
        )
        self._status_icon = Gtk.Image()
        self._status_icon.set_visible(False)
        self._status_bar.append(self._status_icon)
        self._status_label = Gtk.Label(label="Ready", xalign=0, hexpand=True,
                                       ellipsize=Pango.EllipsizeMode.END)
        self._status_label.add_css_class("dim-label")
        self._status_bar.append(self._status_label)
        self._progress = Gtk.ProgressBar()
        self._progress.set_size_request(200, -1)
        self._progress.set_valign(Gtk.Align.CENTER)
        self._progress.set_visible(False)
        self._status_bar.append(self._progress)
        toolbar.add_bottom_bar(self._status_bar)
        self._pulse_source = None

        self._content_stack = Gtk.Stack()
        self._toast_overlay.set_child(self._content_stack)

        # Connecting state
        connecting = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
        )
        conn_spinner = Gtk.Spinner()
        conn_spinner.set_size_request(48, 48)
        conn_spinner.start()
        connecting.append(conn_spinner)
        connecting.append(Gtk.Label(label=f"Connecting to {self._session.hostname}\u2026"))
        self._content_stack.add_named(connecting, "connecting")

        # Ready state: paned with two panes
        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_resize_start_child(True)
        self._paned.set_resize_end_child(True)
        self._paned.set_shrink_start_child(False)
        self._paned.set_shrink_end_child(False)

        left = self._wrap_pane("Local", self._make_local_pane())
        right = self._wrap_pane("Remote", self._make_remote_pane())
        self._paned.set_start_child(left)
        self._paned.set_end_child(right)
        self._content_stack.add_named(self._paned, "ready")

        # Split position — defer until allocation so it honors the split.
        GLib.idle_add(lambda: self._paned.set_position(self.get_width() // 2) or False)

        # Error state
        error_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
            margin_start=40, margin_end=40,
        )
        self._error_label = Gtk.Label(wrap=True, max_width_chars=80)
        self._error_label.add_css_class("title-3")
        error_box.append(self._error_label)
        retry_btn = Gtk.Button(label="Retry")
        retry_btn.set_halign(Gtk.Align.CENTER)
        retry_btn.add_css_class("suggested-action")
        retry_btn.connect("clicked", self._on_retry)
        error_box.append(retry_btn)
        self._content_stack.add_named(error_box, "error")

        self._content_stack.set_visible_child_name("connecting")

    def _wrap_pane(self, title, pane):
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Gtk.Label(label=title, xalign=0,
                          margin_start=12, margin_top=6, margin_bottom=2)
        header.add_css_class("heading")
        frame.append(header)
        frame.append(pane)
        return frame

    def _make_local_pane(self):
        self._local_pane = LocalPane()
        self._local_pane.connect("upload-requested", self._on_upload_requested)
        self._local_pane.connect("status", lambda _p, msg: self.show_toast(msg))
        return self._local_pane

    def _make_remote_pane(self):
        self._remote_pane = RemotePane(self._backend)
        self._remote_pane.connect("download-requested", self._on_download_requested)
        self._remote_pane.connect("status", lambda _p, msg: self.show_toast(msg))
        self._remote_pane.connect("operation-started", self._on_operation_started)
        self._remote_pane.connect("operation-progress", self._on_operation_progress)
        self._remote_pane.connect("operation-finished", self._on_operation_finished)
        return self._remote_pane

    def _on_operation_started(self, _pane, label):
        self._start_progress()
        self._status_label.set_label(label)

    def _on_operation_progress(self, _pane, message):
        if self._pulse_source is not None:
            self._status_label.set_label(message)

    def _on_operation_finished(self, _pane, success, message):
        self._finish_status(success, message)

    # === Backend lifecycle ===

    def _start_backend(self):
        if self._backend is not None:
            self._backend.close()
        self._backend = PsftpBackend(self._session, password=self._password)
        self._backend.connect("disconnected", self._on_backend_disconnected)
        self._remote_pane._backend = self._backend
        self._content_stack.set_visible_child_name("connecting")
        self._backend.start(self._on_backend_ready, self._on_backend_error)

    def _prompt_password(self, heading, is_retry):
        dialog = Adw.AlertDialog(
            heading=heading,
            body=f"Enter password for {self._session.username}@{self._session.hostname}",
        )
        pw_entry = Gtk.Entry()
        pw_entry.set_visibility(False)
        pw_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        pw_entry.set_activates_default(True)
        pw_entry.set_margin_top(8)
        dialog.set_extra_child(pw_entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("connect", "Connect")
        dialog.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("connect")
        dialog.set_close_response("cancel")

        def _resp(_d, response):
            if response == "connect":
                self._password = pw_entry.get_text()
                self._start_backend()
            elif is_retry:
                pass
            else:
                self.close()

        dialog.connect("response", _resp)
        dialog.present(self)
        return False

    def _on_backend_ready(self, home_path):
        self._remote_pane.set_initial_cwd(home_path)
        self._content_stack.set_visible_child_name("ready")
        return False

    def _on_backend_error(self, error):
        self._error_label.set_label(f"Connection failed\n\n{error}")
        self._content_stack.set_visible_child_name("error")
        return False

    def _on_backend_disconnected(self, _backend, error):
        if not self.get_visible():
            return
        self._error_label.set_label(f"Disconnected\n\n{error}")
        self._content_stack.set_visible_child_name("error")

    def _on_retry(self, _btn):
        # If no key, re-prompt for password so the user can correct a typo.
        if not self._session.identity_file:
            self._prompt_password("Reconnect", is_retry=True)
        else:
            self._start_backend()

    # === Transfers ===

    def _on_upload_requested(self, _pane, local_paths):
        if not local_paths:
            return
        self._run_transfer(local_paths, self._remote_pane.get_cwd(), is_upload=True)

    def _on_download_requested(self, _pane, remote_entries):
        if not remote_entries:
            return
        self._run_transfer(remote_entries, self._local_pane.get_cwd(), is_upload=False)

    def _run_transfer(self, items, dest, is_upload):
        self._start_progress()
        self._transfer_step(items, dest, is_upload, 0, success_count=0)

    # === Progress bar ===

    def _start_progress(self):
        self._progress.set_visible(True)
        self._status_icon.set_visible(False)
        self._status_label.remove_css_class("success")
        self._status_label.remove_css_class("error")
        self._status_label.remove_css_class("dim-label")
        if self._pulse_source is None:
            self._pulse_source = GLib.timeout_add(120, self._pulse_tick)

    def _pulse_tick(self):
        self._progress.pulse()
        return True

    def _stop_progress(self, success_count, total, is_upload, any_failed):
        verb = "Uploaded" if is_upload else "Downloaded"
        if any_failed:
            self._finish_status(False, f"{verb} {success_count} of {total}, some failed")
        else:
            self._finish_status(True, f"{verb} {success_count} of {total} \u2014 Done")

    def _finish_status(self, success, message):
        """Stop the pulsing bar and show a success/failure summary for 5s."""
        if self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
        self._progress.set_visible(False)
        icon = "emblem-ok-symbolic" if success else "dialog-error-symbolic"
        css = "success" if success else "error"
        self._status_icon.set_from_icon_name(icon)
        self._status_icon.set_visible(True)
        self._status_label.remove_css_class("dim-label")
        self._status_label.add_css_class(css)
        self._status_label.set_label(message)
        GLib.timeout_add_seconds(5, self._reset_status)

    def _reset_status(self):
        # Only reset if no new transfer started in the meantime.
        if self._pulse_source is not None:
            return False
        self._status_icon.set_visible(False)
        self._status_label.remove_css_class("success")
        self._status_label.remove_css_class("error")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_label("Ready")
        return False

    def _transfer_step(self, items, dest, is_upload, idx, success_count, fail_count=0):
        if idx >= len(items):
            self._stop_progress(success_count, len(items), is_upload, fail_count > 0)
            if is_upload:
                self._remote_pane.refresh()
            else:
                self._local_pane.refresh()
            return

        item = items[idx]
        if is_upload:
            local_path = item
            name = os.path.basename(local_path)
            remote_path = dest.rstrip("/") + "/" + name
            recursive = os.path.isdir(local_path)
            verb = "Uploading folder" if recursive else "Uploading"
            self._status_label.set_label(f"{verb} {name} ({idx + 1}/{len(items)})")
            self._backend.upload(
                local_path, remote_path,
                lambda ok, err: self._on_step_done(items, dest, is_upload, idx, success_count, fail_count, ok, err, name),
                recursive=recursive,
            )
        else:
            entry = item
            remote_path = self._remote_pane.get_cwd().rstrip("/") + "/" + entry.name
            local_path = os.path.join(dest, entry.name)
            recursive = entry.is_dir
            verb = "Downloading folder" if recursive else "Downloading"
            self._status_label.set_label(f"{verb} {entry.name} ({idx + 1}/{len(items)})")
            self._backend.download(
                remote_path, local_path,
                lambda ok, err: self._on_step_done(items, dest, is_upload, idx, success_count, fail_count, ok, err, entry.name),
                recursive=recursive,
            )

    def _on_step_done(self, items, dest, is_upload, idx, success_count, fail_count, ok, err, name):
        if not ok:
            self.show_toast(f"Failed on {name}: {err}")
            fail_count += 1
        else:
            success_count += 1
        self._transfer_step(items, dest, is_upload, idx + 1, success_count, fail_count)

    # === Utilities ===

    def show_toast(self, message):
        self._toast_overlay.add_toast(Adw.Toast(title=message, timeout=3))

    def _on_close_request(self, *_args):
        if self._backend is not None:
            self._backend.close()
        return False
