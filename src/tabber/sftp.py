"""SFTP quick transfer using psftp."""

import os
import subprocess
import threading

from gi.repository import Adw, GLib, GObject, Gtk


class SftpTransferDialog(Adw.Dialog):
    """Dialog for quick SFTP file transfer."""

    def __init__(self, session, window, **kwargs):
        super().__init__(**kwargs)
        self._session = session
        self._window = window
        self._process = None
        self.set_title("SFTP Transfer")
        self.set_content_width(480)
        self.set_content_height(400)
        self._build_ui()

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        header = Adw.HeaderBar()
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _: self.close())
        header.pack_start(close_btn)
        toolbar.add_top_bar(header)

        page = Adw.PreferencesPage()

        # Connection info
        info_group = Adw.PreferencesGroup(title="Connection")
        info_row = Adw.ActionRow(title=self._session.name,
                                  subtitle=self._session.connection_string)
        info_row.set_icon_name("network-server-symbolic")
        info_group.add(info_row)
        page.add(info_group)

        # Upload group
        upload_group = Adw.PreferencesGroup(title="Upload File")

        self._local_file_row = Adw.EntryRow(title="Local File")
        browse_btn = Gtk.Button(icon_name="document-open-symbolic",
                                valign=Gtk.Align.CENTER, tooltip_text="Browse")
        browse_btn.add_css_class("flat")
        browse_btn.connect("clicked", self._on_browse_local)
        self._local_file_row.add_suffix(browse_btn)
        upload_group.add(self._local_file_row)

        self._remote_path_row = Adw.EntryRow(title="Remote Path (e.g. /home/user/)")
        upload_group.add(self._remote_path_row)

        upload_btn = Gtk.Button(label="Upload")
        upload_btn.add_css_class("suggested-action")
        upload_btn.set_margin_top(8)
        upload_btn.set_halign(Gtk.Align.END)
        upload_btn.connect("clicked", self._on_upload)
        upload_group.add(upload_btn)

        page.add(upload_group)

        # Download group
        download_group = Adw.PreferencesGroup(title="Download File")

        self._remote_file_row = Adw.EntryRow(title="Remote File Path")
        download_group.add(self._remote_file_row)

        self._local_dir_row = Adw.EntryRow(title="Save To (local directory)")
        self._local_dir_row.set_text(str(os.path.expanduser("~/Downloads")))
        download_group.add(self._local_dir_row)

        download_btn = Gtk.Button(label="Download")
        download_btn.add_css_class("suggested-action")
        download_btn.set_margin_top(8)
        download_btn.set_halign(Gtk.Align.END)
        download_btn.connect("clicked", self._on_download)
        download_group.add(download_btn)

        page.add(download_group)

        # Status
        self._status_group = Adw.PreferencesGroup(title="Status")
        self._status_label = Gtk.Label(label="Ready", xalign=0, wrap=True,
                                        margin_start=12, margin_end=12, margin_top=4, margin_bottom=4)
        self._status_group.add(self._status_label)
        self._progress = Gtk.ProgressBar()
        self._progress.set_margin_start(12)
        self._progress.set_margin_end(12)
        self._progress.set_margin_bottom(8)
        self._progress.set_visible(False)
        self._status_group.add(self._progress)
        page.add(self._status_group)

        scroll = Gtk.ScrolledWindow(vexpand=True, child=page)
        toolbar.set_content(scroll)

    def _build_psftp_args(self):
        s = self._session
        args = ["psftp"]
        if s.username:
            args.extend(["-l", s.username])
        if s.port and s.port != 22:
            args.extend(["-P", str(s.port)])
        if s.identity_file:
            args.extend(["-i", s.identity_file])
        args.append(s.hostname)
        return args

    def _on_browse_local(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Select File to Upload")
        dialog.open(self.get_root(), None, self._on_file_selected)

    def _on_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self._local_file_row.set_text(file.get_path())
        except Exception:
            pass

    def _on_upload(self, _btn):
        local_file = self._local_file_row.get_text().strip()
        remote_path = self._remote_path_row.get_text().strip()
        if not local_file or not remote_path:
            self._status_label.set_text("Please fill in both fields")
            return
        if not os.path.exists(local_file):
            self._status_label.set_text("Local file not found")
            return

        command = f'put "{local_file}" "{remote_path}"\nquit\n'
        self._run_psftp(command, f"Uploading {os.path.basename(local_file)}...")

    def _on_download(self, _btn):
        remote_file = self._remote_file_row.get_text().strip()
        local_dir = self._local_dir_row.get_text().strip()
        if not remote_file or not local_dir:
            self._status_label.set_text("Please fill in both fields")
            return

        filename = os.path.basename(remote_file)
        local_path = os.path.join(local_dir, filename)
        command = f'get "{remote_file}" "{local_path}"\nquit\n'
        self._run_psftp(command, f"Downloading {filename}...")

    def _run_psftp(self, commands, status_message):
        self._status_label.set_text(status_message)
        self._progress.set_visible(True)
        self._progress.pulse()

        def _worker():
            try:
                args = self._build_psftp_args()
                proc = subprocess.run(
                    args,
                    input=commands,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode == 0:
                    GLib.idle_add(self._transfer_done, True, "Transfer complete!")
                else:
                    error = proc.stderr.strip() or proc.stdout.strip() or "Unknown error"
                    GLib.idle_add(self._transfer_done, False, f"Error: {error[:200]}")
            except subprocess.TimeoutExpired:
                GLib.idle_add(self._transfer_done, False, "Transfer timed out")
            except Exception as e:
                GLib.idle_add(self._transfer_done, False, f"Error: {e}")

        # Pulse the progress bar while working
        self._pulse_id = GLib.timeout_add(200, self._pulse_progress)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _pulse_progress(self):
        if self._progress.get_visible():
            self._progress.pulse()
            return True
        return False

    def _transfer_done(self, success, message):
        self._progress.set_visible(False)
        if hasattr(self, "_pulse_id"):
            GLib.source_remove(self._pulse_id)
        self._status_label.set_text(message)
        if success and self._window:
            self._window.show_toast(message)
