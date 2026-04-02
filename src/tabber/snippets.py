"""Command snippets library - save and paste frequent commands."""

import json
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk

CONFIG_DIR = Path.home() / ".config" / "tabber"
SNIPPETS_FILE = CONFIG_DIR / "snippets.json"


def load_snippets():
    """Load snippets from disk."""
    if SNIPPETS_FILE.exists():
        try:
            with open(SNIPPETS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_snippets(snippets):
    """Save snippets to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNIPPETS_FILE, "w") as f:
        json.dump(snippets, f, indent=2)


def add_snippet(name, command, category="General"):
    snippets = load_snippets()
    snippets.append({"name": name, "command": command, "category": category})
    save_snippets(snippets)


def delete_snippet(index):
    snippets = load_snippets()
    if 0 <= index < len(snippets):
        snippets.pop(index)
        save_snippets(snippets)


class SnippetDialog(Adw.Dialog):
    """Dialog for adding/editing a snippet."""

    __gsignals__ = {
        "snippet-saved": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, snippet=None, **kwargs):
        super().__init__(**kwargs)
        self._snippet = snippet
        self.set_title("Edit Snippet" if snippet else "New Snippet")
        self.set_content_width(400)
        self.set_content_height(320)
        self._build_ui()

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        header = Adw.HeaderBar()
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)
        toolbar.add_top_bar(header)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Snippet")

        self._name_row = Adw.EntryRow(title="Name")
        group.add(self._name_row)

        self._category_row = Adw.EntryRow(title="Category")
        self._category_row.set_text("General")
        group.add(self._category_row)

        self._command_row = Adw.EntryRow(title="Command")
        group.add(self._command_row)

        # Hint
        hint = Gtk.Label(
            label="Use \\n for newline, \\t for tab. The command is sent exactly as typed.",
            wrap=True, xalign=0, opacity=0.6,
            margin_start=12, margin_end=12, margin_top=6,
        )
        group.add(hint)

        page.add(group)

        scroll = Gtk.ScrolledWindow(vexpand=True, child=page)
        toolbar.set_content(scroll)

        if self._snippet:
            self._name_row.set_text(self._snippet.get("name", ""))
            self._category_row.set_text(self._snippet.get("category", "General"))
            self._command_row.set_text(self._snippet.get("command", ""))

    def _on_save(self, _btn):
        name = self._name_row.get_text().strip()
        command = self._command_row.get_text().strip()
        category = self._category_row.get_text().strip() or "General"
        if not name or not command:
            return
        add_snippet(name, command, category)
        self.emit("snippet-saved")
        self.close()


class SnippetsPanel(Gtk.Box):
    """A panel showing saved command snippets, to be shown in a popover or sidebar."""

    __gsignals__ = {
        "snippet-activated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.set_size_request(280, 300)

        # Header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                             margin_start=12, margin_end=12, margin_top=8, margin_bottom=4)
        header_label = Gtk.Label(label="Command Snippets", hexpand=True, xalign=0)
        header_label.add_css_class("heading")
        header_box.append(header_label)

        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New Snippet")
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", self._on_add)
        header_box.append(add_btn)
        self.append(header_box)

        # Snippet list
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_margin_start(8)
        self._listbox.set_margin_end(8)
        self._listbox.set_margin_bottom(8)
        scroll.set_child(self._listbox)
        self.append(scroll)

        self.refresh()

    def refresh(self):
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)

        snippets = load_snippets()
        if not snippets:
            placeholder = Gtk.Label(
                label="No snippets yet.\nClick + to add one.",
                margin_top=20, opacity=0.5,
            )
            self._listbox.set_placeholder(placeholder)
            return

        for i, snippet in enumerate(snippets):
            row = Adw.ActionRow()
            row.set_title(snippet["name"])
            row.set_subtitle(snippet.get("command", "")[:60])

            # Run button
            run_btn = Gtk.Button(icon_name="media-playback-start-symbolic",
                                 valign=Gtk.Align.CENTER, tooltip_text="Send to terminal")
            run_btn.add_css_class("flat")
            run_btn.connect("clicked", self._on_run, snippet["command"])
            row.add_suffix(run_btn)

            # Delete button
            del_btn = Gtk.Button(icon_name="user-trash-symbolic",
                                 valign=Gtk.Align.CENTER, tooltip_text="Delete")
            del_btn.add_css_class("flat")
            del_btn.connect("clicked", self._on_delete, i)
            row.add_suffix(del_btn)

            self._listbox.append(row)

    def _on_add(self, _btn):
        dialog = SnippetDialog()
        dialog.connect("snippet-saved", lambda _: self.refresh())
        # Find the window to present from
        win = self.get_root()
        if win:
            dialog.present(win)

    def _on_run(self, _btn, command):
        # Unescape \n and \t
        text = command.replace("\\n", "\n").replace("\\t", "\t")
        self.emit("snippet-activated", text)

    def _on_delete(self, _btn, index):
        delete_snippet(index)
        self.refresh()
