"""Persistent psftp subprocess with nonce-framed request/response protocol.

The fragility of parsing psftp output comes from three places:
1. Not knowing where one command's output ends and the next begins.
2. Locale-dependent date formats in `ls -l`.
3. Shared prompt string inlined with command output on the same line.

We address each:
1. Every command is framed with `!echo __BEGIN_<nonce>__` and `!echo __END_<nonce>__`.
   The reader thread matches these markers to carve the stream into frames. A fresh
   64-bit random nonce per command makes collisions with filenames impossible.
2. We set LC_ALL=C in psftp's environment for stable English output.
3. Any line starting with `psftp> ` has that prefix stripped before parsing.
"""

import os
import queue
import re
import secrets
import subprocess
import threading
from dataclasses import dataclass

from gi.repository import GLib, GObject


@dataclass
class RemoteEntry:
    name: str
    is_dir: bool
    is_link: bool
    size: int
    mtime: str
    mode: str
    owner: str = ""
    group: str = ""


_PERMS_RE = re.compile(r"^[dlbcps-][rwxsStT-]{9}\.?$")


def _parse_ls_line(line):
    """Parse one line of `ls -l` output. Returns RemoteEntry or None."""
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None
    perms, links, owner, group, size, month, day, time_or_year, name = parts
    if not _PERMS_RE.match(perms):
        return None
    if not links.isdigit() or not size.isdigit():
        return None
    is_dir = perms[0] == "d"
    is_link = perms[0] == "l"
    if is_link and " -> " in name:
        name = name.split(" -> ", 1)[0]
    if name in (".", ".."):
        return None
    return RemoteEntry(
        name=name,
        is_dir=is_dir,
        is_link=is_link,
        size=int(size),
        mtime=f"{month} {day} {time_or_year}",
        mode=perms,
        owner=owner,
        group=group,
    )


def _psftp_quote(path):
    """Quote a path for psftp. psftp parses double-quoted strings with backslash escapes."""
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class PsftpBackend(GObject.Object):
    """Persistent psftp subprocess. All public methods marshal callbacks back to the
    UI thread via GLib.idle_add."""

    __gsignals__ = {
        "disconnected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, session, password=None):
        super().__init__()
        self._session = session
        self._password = password
        self._proc = None
        self._alive = False
        self._command_queue = queue.Queue()
        self._pending = {}  # nonce -> {on_done, stdout, stderr}
        self._lock = threading.Lock()
        self._writer_thread = None
        self._stdout_thread = None
        self._stderr_thread = None
        self._startup_stderr = []  # captured before any command is in-flight

    # === Public API ===

    def start(self, on_ready, on_error):
        """Spawn psftp and verify readiness via an initial `pwd` command."""
        args = self._build_args()
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            GLib.idle_add(on_error, "psftp not found. Install the putty-tools package.")
            return
        except Exception as e:
            GLib.idle_add(on_error, f"Failed to start psftp: {e}")
            return

        self._alive = True
        self._stdout_thread = threading.Thread(target=self._stdout_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._writer_thread.start()

        def _first(result):
            if result["ok"]:
                home = result["stdout"][0].strip() if result["stdout"] else "/"
                # psftp's pwd prints "Remote directory is /home/user"
                if home.startswith("Remote directory is "):
                    home = home[len("Remote directory is "):].strip()
                GLib.idle_add(on_ready, home)
            else:
                err = result["error"] or "Failed to connect"
                GLib.idle_add(on_error, err)
        self._send("pwd", _first, timeout=30)

    def list_dir(self, path, callback):
        """callback(entries_or_None, error_or_None) on UI thread."""
        def _done(result):
            if not result["ok"]:
                GLib.idle_add(callback, None, result["error"])
                return
            entries = []
            for line in result["stdout"]:
                entry = _parse_ls_line(line)
                if entry:
                    entries.append(entry)
            GLib.idle_add(callback, entries, None)
        # psftp's `ls` takes only a path (no unix-style flags); it already
        # shows all entries including hidden files and uses long format.
        self._send(f"ls {_psftp_quote(path)}", _done)

    def make_dir(self, path, callback):
        self._send(f"mkdir {_psftp_quote(path)}",
                   lambda r: GLib.idle_add(callback, r["ok"], r["error"]))

    def remove_dir(self, path, callback):
        """Recursive remove: psftp's rmdir only works on empty dirs, so we
        list the contents, delete each child (recursing for subdirs), then
        finally rmdir the target. `callback(ok, error)` on UI thread."""
        self._recursive_remove(path, callback)

    def _recursive_remove(self, path, callback):
        def _after_ls(entries, err):
            if err is not None:
                GLib.idle_add(callback, False, err)
                return
            self._remove_children_then_rmdir(path, entries, 0, callback)
        self.list_dir(path, _after_ls)

    def _remove_children_then_rmdir(self, path, entries, idx, callback):
        if idx >= len(entries):
            self._send(
                f"rmdir {_psftp_quote(path)}",
                lambda r: GLib.idle_add(callback, True, None),
            )
            return
        entry = entries[idx]
        child = path.rstrip("/") + "/" + entry.name

        def _next(ok, err):
            if not ok:
                GLib.idle_add(callback, False, err)
                return
            self._remove_children_then_rmdir(path, entries, idx + 1, callback)

        if entry.is_dir and not entry.is_link:
            self._recursive_remove(child, _next)
        else:
            self._send(
                f"rm {_psftp_quote(child)}",
                lambda r: GLib.idle_add(_next, True, None),
            )

    def delete_file(self, path, callback):
        self._send(f"rm {_psftp_quote(path)}",
                   lambda r: GLib.idle_add(callback, r["ok"], r["error"]))

    def rename(self, src, dst, callback):
        self._send(f"mv {_psftp_quote(src)} {_psftp_quote(dst)}",
                   lambda r: GLib.idle_add(callback, r["ok"], r["error"]))

    def upload(self, local, remote, callback, recursive=False):
        flag = "-r " if recursive else ""
        self._send(f"put {flag}{_psftp_quote(local)} {_psftp_quote(remote)}",
                   lambda r: GLib.idle_add(callback, r["ok"], r["error"]),
                   timeout=3600)

    def download(self, remote, local, callback, recursive=False):
        flag = "-r " if recursive else ""
        self._send(f"get {flag}{_psftp_quote(remote)} {_psftp_quote(local)}",
                   lambda r: GLib.idle_add(callback, r["ok"], r["error"]),
                   timeout=3600)

    def close(self):
        self._alive = False
        self._command_queue.put(None)
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()

    # === Internal ===

    def _build_args(self):
        s = self._session
        args = ["psftp", "-batch"]
        if s.username:
            args.extend(["-l", s.username])
        if s.port and s.port != 22:
            args.extend(["-P", str(s.port)])
        if s.identity_file:
            args.extend(["-i", s.identity_file])
        if self._password:
            # Note: psftp -pw exposes the password in the process list (ps aux)
            # for the lifetime of the subprocess. Acceptable for this workflow;
            # the alternative is PTY-based password injection which is complex.
            args.extend(["-pw", self._password])
        if s.compression:
            args.append("-C")
        if s.agent_forward:
            args.append("-A")
        if s.jump_host:
            args.extend(["-J", s.jump_host])
        if s.proxy_command:
            args.extend(["-proxycmd", s.proxy_command])
        if s.ip_version == "4":
            args.append("-4")
        elif s.ip_version == "6":
            args.append("-6")
        args.append(s.hostname)
        return args

    def _send(self, cmd, on_done, timeout=60):
        self._command_queue.put((cmd, on_done, timeout))

    def _writer_loop(self):
        """Serialize command execution: only one frame in flight at a time."""
        while self._alive:
            item = self._command_queue.get()
            if item is None:
                break
            cmd, on_done, timeout = item
            self._run_one(cmd, on_done, timeout)

    def _run_one(self, cmd, on_done, timeout):
        nonce = secrets.token_hex(8)
        done_event = threading.Event()
        result_box = [None]

        def _collector(result):
            result_box[0] = result
            done_event.set()

        with self._lock:
            self._pending[nonce] = {"on_done": _collector, "stdout": [], "stderr": []}

        script = f"!echo __BEGIN_{nonce}__\n{cmd}\n!echo __END_{nonce}__\n"
        try:
            self._proc.stdin.write(script)
            self._proc.stdin.flush()
        except Exception as e:
            with self._lock:
                self._pending.pop(nonce, None)
            on_done({"ok": False, "stdout": [], "stderr": [], "error": f"Write failed: {e}"})
            return

        completed = done_event.wait(timeout=timeout)
        if not completed:
            with self._lock:
                self._pending.pop(nonce, None)
            on_done({"ok": False, "stdout": [], "stderr": [],
                     "error": f"Command timed out after {timeout}s"})
            return

        on_done(result_box[0])

    def _stdout_loop(self):
        begin_re = re.compile(r"^__BEGIN_([0-9a-f]{16})__\s*$")
        end_re = re.compile(r"^__END_([0-9a-f]{16})__\s*$")
        current = None
        try:
            for raw_line in self._proc.stdout:
                if not self._alive:
                    break
                line = raw_line.rstrip("\r\n")
                # Strip any inline prompts (can appear at line start when psftp
                # prints its next prompt immediately before the command's first
                # output line arrives on the same line).
                while line.startswith("psftp> "):
                    line = line[len("psftp> "):]
                m = begin_re.match(line)
                if m:
                    current = m.group(1)
                    continue
                m = end_re.match(line)
                if m:
                    nonce = m.group(1)
                    with self._lock:
                        fut = self._pending.pop(nonce, None)
                    if fut:
                        # Frame completed — command executed. Stderr captured
                        # during a frame (e.g. psftp's "Using username" banner)
                        # is informational, not an error. Process-exit stderr
                        # is handled separately in _drain_on_exit.
                        fut["on_done"]({
                            "ok": True,
                            "stdout": fut["stdout"],
                            "stderr": fut["stderr"],
                            "error": None,
                        })
                    current = None
                    continue
                if current:
                    with self._lock:
                        fut = self._pending.get(current)
                        if fut:
                            fut["stdout"].append(line)
        except Exception:
            pass
        finally:
            # Give stderr reader a moment to flush any remaining diagnostic
            # lines so we can include them in the error.
            if self._stderr_thread and self._stderr_thread.is_alive():
                self._stderr_thread.join(timeout=0.5)
            msg = "psftp process exited"
            with self._lock:
                startup = "\n".join(self._startup_stderr).strip()
            if startup:
                msg = startup
            self._drain_on_exit(msg)

    def _stderr_loop(self):
        try:
            for raw_line in self._proc.stderr:
                if not self._alive:
                    break
                line = raw_line.rstrip("\r\n")
                # Attribute to the single currently-in-flight frame (we serialize,
                # so there is at most one). If no frame is pending, buffer it so
                # an early exit error can still be reported.
                with self._lock:
                    if self._pending:
                        nonce = next(iter(self._pending))
                        self._pending[nonce]["stderr"].append(line)
                    else:
                        self._startup_stderr.append(line)
        except Exception:
            pass

    def _drain_on_exit(self, error):
        was_alive = self._alive
        self._alive = False
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for nonce, fut in pending:
            # Prefer the frame's own stderr lines (actual psftp diagnostic)
            # over the generic "process exited" message.
            fut_err = "\n".join(fut["stderr"]).strip()
            fut["on_done"]({
                "ok": False, "stdout": fut["stdout"], "stderr": fut["stderr"],
                "error": fut_err or error,
            })
        if was_alive:
            GLib.idle_add(self._emit_disconnected, error)

    def _emit_disconnected(self, error):
        self.emit("disconnected", error)
        return False
