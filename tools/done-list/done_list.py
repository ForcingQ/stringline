#!/usr/bin/env python3
"""done-list: checks a finished list, and runs as a Claude Code Stop hook.

How it is fired: by hand, python3 tools/done-list/done_list.py check <list>
(a real run, one row in runs/); as a Stop hook of type command, armed by a
settings entry that names the list (--help prints it; nothing in this
repository installs it); report <list> reads the hook's own log; its self-test
with --selftest.

The failure that earned it: a list written in a shape its own checker could
not read, and a line that passed before any work was done.

What it does not prove: that a check measures the work (it runs what the list
holds, and a weak command passes weak work); that a YOURS stop was honoured
(a stop line is the agent's own and can be forged; the log is the record);
that the hook reaches a background seat (it acts on Stop only).

Shape (SPEC-done-list.md): one block in a markdown file, between
<!-- done-list root="..." cap=3 timeout=60 --> and <!-- /done-list -->, each
non-blank line an item `n. **TAG** — <what is true> · <proof>`, a RESCOPE line,
or MALFORMED. Three states, always: DONE, NOT DONE, CAN'T TELL, plus MALFORMED
for a line that is not an item. Python 3.11 or later, standard library only,
plus git; the run log is the shared tools/runlog.py, imported by path.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import runlog  # noqa: E402  (tools/runlog.py, the shared writer)

TOOL = "done-list"
FILES = ["tools/done-list/done_list.py", "tools/runlog.py"]
EARNED_BY = ("A list written in a shape its own checker could not read, and a line"
             " that passed before any work was done.")
TAGS = ("POINTABLE", "YOURS", "WITNESSED", "CONDITIONAL", "UNSORTED")
CAP_MAX, CAP_DEFAULT, TIMEOUT_DEFAULT = 3, 3, 60
OPEN_RE = re.compile(r"<!--\s*done-list(?=[\s>-])(.*?)-->")
CLOSE_RE = re.compile(r"<!--\s*/done-list\s*-->")
ATTR_RE = re.compile(r'\s*([A-Za-z_][\w-]*)=("([^"]*)"|[^\s"]+)')
ITEM_RE = re.compile(r"(\d+)\. \*\*([^*]+)\*\* — (.*)")
RESCOPE_RE = re.compile(r"- RESCOPE\b")
YOURS_RE = re.compile(r"STOP: YOURS #(\d+)")
BLOCKED_RE = re.compile(r"STOP: BLOCKED #(\d+): \S.*")
BEFORE_OK = "[before-work ok]"

SETTINGS = """{"hooks": {"Stop": [{"hooks": [{"type": "command",
  "command": "python3 <abs path>/tools/done-list/done_list.py hook --list <abs path of the list>",
  "timeout": <seconds>}]}]}}"""

HELP_EPILOG = f"""\
Arm the hook (by hand; nothing in this repository installs it) with this entry
in a project's .claude/settings.json, or its local, ignored one:

{SETTINGS}

Set "timeout" above one run of the list's checks: the sum of their timeouts,
since every fire runs them all once. A hook the harness kills leaves a fired
line with no acted line in its log, and report counts it as killed.

The hook allows the stop when the last message's last non-blank line is
STOP: YOURS #n or STOP: BLOCKED #n: <what blocks it>, when every POINTABLE
exits 0 and no line is malformed, when the cap is reached, when the list
cannot be opened, and on its own error (fail-open, logged). Otherwise it
blocks with the open items. Its counter and log sit in .done-list/ beside the
list, or in --state <dir>.

What it cannot see: whether a check measures the work (it runs what the list
holds, read-only by the author's word only); whether a YOURS stop was
honoured, or a stop line forged (every stop line is the agent's own); whether
the hook reaches a background seat or a subagent (it acts on Stop only); a
stop line anywhere but the last non-blank line of the last message; a
transcript whose events differ from the shape it reads (one part, text,
thinking or tool_use, per assistant event); whether a WITNESSED record says the
seeing was good (it sees only that the file exists).
"""


# ---------------------------------------------------------------- the list

class NotAList(Exception):
    """A file that opens but holds no single, closed, non-empty block."""


class Line:
    """One non-blank line of the block, read."""

    def __init__(self, lineno, text):
        self.lineno, self.text = lineno, text
        self.num = self.tag = self.why = self.command = None
        self.before_ok = False
        self.path = None  # YOURS words, WITNESSED evidence

    @property
    def label(self):
        return f"#{self.num}" if self.num is not None else f"line {self.lineno}"


def _attrs(raw, lineno):
    """The opener's attributes, and a malformed Line for each bad one."""
    found, bad, pos = {}, [], 0
    raw = raw.strip()
    while pos < len(raw):
        m = ATTR_RE.match(raw, pos)
        if not m:
            bad.append("an attribute that is not key=value")
            break
        found[m.group(1)] = m.group(3) if m.group(3) is not None else m.group(2)
        pos = m.end()
    notes = []
    cap, timeout = CAP_DEFAULT, TIMEOUT_DEFAULT
    if "cap" in found:
        v = found["cap"]
        if not re.fullmatch(r"\d+", v) or int(v) < 1:
            bad.append("cap is not a whole number of 1 or more")
        elif int(v) > CAP_MAX:
            notes.append(f"cap {v} read as {CAP_MAX}, the most allowed")
        else:
            cap = int(v)
    if "timeout" in found:
        v = found["timeout"]
        if not re.fullmatch(r"\d+", v) or int(v) < 1:
            bad.append("timeout is not a whole number of seconds")
        else:
            timeout = int(v)
    for key in found:
        if key not in ("root", "cap", "timeout"):
            notes.append(f"attribute {key} is not one this tool reads; ignored")
    lines = []
    for why in bad:
        line = Line(lineno, "")
        line.tag, line.why = "MALFORMED", why
        lines.append(line)
    return found.get("root"), cap, timeout, notes, lines


def _command(rest):
    """The POINTABLE command: from the first backtick after check: to the last
    backtick on the line. Returns (command, text outside it, why malformed)."""
    at = rest.find("check:")
    if at < 0:
        return None, rest, "a POINTABLE with no check: command"
    first = rest.find("`", at)
    last = rest.rfind("`")
    if first < 0 or last <= first:
        return None, rest, "a POINTABLE with no command in backticks"
    cmd = rest[first + 1:last]
    outside = rest[:first] + rest[last + 1:]
    if "`" in cmd:
        return None, outside, ("a backtick inside the command (a nested backtick,"
                               " or a code span in the note after it)")
    if not cmd.strip():
        return None, outside, "a POINTABLE with an empty command"
    return cmd, outside, None


def _path_after(rest, key):
    """The path after `key:`, in backticks or up to the next ' · '."""
    at = rest.find(key + ":")
    if at < 0:
        return None
    tail = rest[at + len(key) + 1:].strip()
    if tail.startswith("`"):
        end = tail.find("`", 1)
        return tail[1:end].strip() if end > 0 else None
    return tail.split(" · ")[0].strip() or None


def _read_line(lineno, text, seen):
    line = Line(lineno, text)
    if RESCOPE_RE.match(text):
        line.tag = "RESCOPE"
        return line
    m = ITEM_RE.fullmatch(text)
    if not m:
        line.tag = "MALFORMED"
        if text[:1].isspace():
            line.why = "a leading space, not an item"
        elif text[:1] in "-*+":
            line.why = "a bullet, not an item"
        elif re.match(r"\d+\)", text):
            line.why = "a bracket after the number, not an item"
        elif re.match(r"\d+\. \*\*[^*]+\*\*", text):
            line.why = "no ' — ' after the tag"
        else:
            line.why = "not an item: n. **TAG** — <what is true> · <proof>"
        num = re.match(r"(\d+)[.)]", text.strip())
        if num:
            line.num = int(num.group(1))
        return line
    line.num, tag, rest = int(m.group(1)), m.group(2), m.group(3)
    if tag not in TAGS:
        line.tag, line.why = "MALFORMED", "a tag that is not one of the five"
        return line
    if line.num in seen:
        line.tag, line.why = "MALFORMED", f"repeats item number {line.num}"
        return line
    seen.add(line.num)
    line.tag = tag
    if tag == "POINTABLE":
        cmd, outside, why = _command(rest)
        if why:
            line.tag, line.why = "MALFORMED", why
            return line
        line.command, line.before_ok = cmd, BEFORE_OK in outside
    elif tag == "YOURS":
        line.path = _path_after(rest, "words")
    elif tag == "WITNESSED":
        line.path = _path_after(rest, "evidence")
    line.rest = rest
    return line


class DoneList:
    """A parsed list: its root, cap, timeout, lines and notes."""

    def __init__(self, path):
        self.path = path
        with open(path, encoding="utf-8") as fh:  # OSError: cannot be opened
            text = fh.read()
        rows = text.splitlines()
        opens = [i for i, r in enumerate(rows) if OPEN_RE.search(r)]
        closes = [i for i, r in enumerate(rows) if CLOSE_RE.search(r)]
        if not opens:
            raise NotAList("no done-list block in the file")
        if len(opens) > 1:
            raise NotAList(f"{len(opens)} done-list blocks in one file (twin): which"
                           " one is the list cannot be told")
        start = opens[0]
        after = [c for c in closes if c > start]
        if not after:
            raise NotAList("the done-list block does not close")
        end = after[0]
        raw_root, self.cap, self.timeout, self.notes, self.lines = _attrs(
            OPEN_RE.search(rows[start]).group(1), start + 1)
        here = os.path.dirname(os.path.abspath(path))
        self.root = os.path.normpath(os.path.join(here, raw_root)) if raw_root else here
        seen = set()
        for i in range(start + 1, end):
            if rows[i].strip():
                self.lines.append(_read_line(i + 1, rows[i], seen))
        if not [x for x in self.lines if x.tag not in ("RESCOPE",)]:
            raise NotAList("the done-list block holds no item")

    def items(self):
        return [x for x in self.lines if x.tag != "RESCOPE"]

    def item(self, num):
        for x in self.lines:
            if x.num == num and x.tag not in ("MALFORMED", "RESCOPE"):
                return x
        return None


# ---------------------------------------------------------------- running

def run_command(cmd, root, timeout):
    """('DONE'|'NOT DONE'|"CAN'T TELL", detail). The command runs through sh -c
    from the root, in its own process group, stdin empty, output discarded."""
    if not os.path.isdir(root):
        return "CAN'T TELL", "the root folder does not exist"
    try:
        proc = subprocess.Popen(["sh", "-c", cmd], cwd=root, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except OSError as exc:
        return "CAN'T TELL", f"could not start ({type(exc).__name__})"
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        return "CAN'T TELL", f"timed out after {timeout}s; its process group ended"
    if code == 0:
        return "DONE", ""
    if code in (126, 127):
        return "CAN'T TELL", f"could not start (exit {code})"
    if code < 0:
        return "CAN'T TELL", f"ended by signal {-code}"
    return "NOT DONE", f"exit {code}"


def _present(path, root):
    if not path:
        return False
    full = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        with open(os.path.expanduser(full), encoding="utf-8", errors="replace") as fh:
            return any(r.strip() for r in fh)
    except OSError:
        return False


def evaluate(dl, before_work=False):
    """Run the list. Returns (printed lines, counts, caught, could_not)."""
    out, caught, could_not = [], [], []
    counts = {"done": 0, "not_done": 0, "cant_tell": 0, "malformed": 0}
    early = 0
    for x in dl.items():
        if x.tag == "MALFORMED":
            counts["malformed"] += 1
            out.append(f"{x.label} MALFORMED ({x.why})")
            caught.append(f"{x.label} malformed ({x.why})")
        elif x.tag == "POINTABLE":
            state, detail = run_command(x.command, dl.root, dl.timeout)
            x.state = state
            if state == "DONE":
                counts["done"] += 1
                if before_work and not x.before_ok:
                    early += 1
                    out.append(f"#{x.num} DONE · CATCH: passes before the work")
                    caught.append(f"#{x.num} passes before the work")
                else:
                    out.append(f"#{x.num} DONE" + (" · marked [before-work ok]"
                                                   if before_work and x.before_ok else ""))
            elif state == "NOT DONE":
                counts["not_done"] += 1
                out.append(f"#{x.num} NOT DONE ({detail})")
            else:
                counts["cant_tell"] += 1
                out.append(f"#{x.num} CAN'T TELL ({detail})")
                could_not.append(f"#{x.num} can't tell: {detail}")
        elif x.tag == "YOURS":
            where = x.path or "(no path named)"
            out.append(f"#{x.num} YOURS · words at {where}: "
                       + ("present" if _present(x.path, dl.root) else "absent"))
        elif x.tag == "WITNESSED":
            out.append(f"#{x.num} WITNESSED · evidence "
                       + ("present" if _present(x.path, dl.root) else "absent"))
        else:
            out.append(f"#{x.num} {x.tag} — {x.rest}")
    if before_work:
        counts["passes_before_work"] = early
    return out, counts, caught, could_not


def _summary(counts):
    return (f"pointable: done {counts['done']} · not done {counts['not_done']}"
            f" · can't tell {counts['cant_tell']} · malformed {counts['malformed']}")


def _rel(path):
    """A path relative to this tool's repository, or the phrase."""
    root = runlog.module_root()
    full = os.path.realpath(path)
    rel = os.path.relpath(full, root)
    if rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
        return runlog.OUTSIDE
    return rel.replace(os.sep, "/") or "."


def _log_row(args, read, against, counts, caught, could_not):
    if args.no_log:
        return
    kind = "planted" if args.planted else "real"
    try:
        path = runlog.write(TOOL, FILES, kind, args.planted or "", "person",
                            [read], [against], counts, caught, could_not)
        print(f"logged: {os.path.relpath(path)}")
    except runlog.RunLogError as exc:
        print(f"no row written: {type(exc).__name__}: {exc}", file=sys.stderr)


def cmd_check(args):
    try:
        dl = DoneList(args.list)
    except NotAList as exc:
        print(f"CAN'T TELL: not a list: {exc}")
        print(f"read: {args.list}")
        _log_row(args, _rel(args.list), _rel(os.path.dirname(os.path.abspath(args.list))),
                 {"done": 0, "not_done": 0, "cant_tell": 0, "malformed": 0}, [],
                 [f"not a list: {exc}"])
        return 2
    except OSError as exc:
        print(f"CAN'T TELL: the list could not be opened ({type(exc).__name__})")
        return 2
    out, counts, caught, could_not = evaluate(dl, args.before_work)
    for line in out:
        print(line)
    print(_summary(counts) + (f" · passes before the work {counts['passes_before_work']}"
                              if args.before_work else ""))
    print(f"read: {args.list} · ran in: {dl.root} · cap {dl.cap} · timeout {dl.timeout}s")
    for note in dl.notes:
        print(f"note: {note}")
    print("could not see: " + ("; ".join(could_not) if could_not else
                               "nothing this run; YOURS and WITNESSED are read as a"
                               " file being there, never as what it says"))
    _log_row(args, _rel(args.list), _rel(dl.root), counts, caught, could_not)
    if counts["not_done"] or counts["malformed"] or counts.get("passes_before_work"):
        return 1
    return 2 if counts["cant_tell"] else 0


# ---------------------------------------------------------------- the hook

def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _state_dir(args):
    return args.state or os.path.join(os.path.dirname(os.path.abspath(args.list)),
                                      ".done-list")


def _log(state, entry):
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "log.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _session_file(state, session):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session or "unknown"))[:120] or "unknown"
    return os.path.join(state, safe + ".json")


def _blocks(state, session):
    try:
        with open(_session_file(state, session), encoding="utf-8") as fh:
            k = json.load(fh).get("blocks", 0)
        return k if isinstance(k, int) and k >= 0 else 0
    except (OSError, ValueError, AttributeError):
        return 0


def _set_blocks(state, session, k):
    os.makedirs(state, exist_ok=True)
    with open(_session_file(state, session), "w", encoding="utf-8") as fh:
        json.dump({"blocks": k}, fh)


def _text_parts(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"]
    return []


def last_message(data):
    """(the last assistant message's text or None, how it was found)."""
    msg = data.get("last_assistant_message")
    if isinstance(msg, str):
        return msg, "last_assistant_message"
    path = data.get("transcript_path")
    if not isinstance(path, str) or not path:
        return None, "no last_assistant_message and no transcript_path"
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            events = []
            for raw in fh:
                try:
                    events.append(json.loads(raw))
                except ValueError:
                    continue
    except OSError as exc:
        return None, f"transcript could not be read ({type(exc).__name__})"
    last_user = -1
    for i, ev in enumerate(events):
        if isinstance(ev, dict) and ev.get("type") == "user":
            last_user = i
    text = None
    for ev in events[last_user + 1:]:
        if not isinstance(ev, dict) or ev.get("type") != "assistant":
            continue
        message = ev.get("message")
        parts = _text_parts(message.get("content") if isinstance(message, dict) else None)
        if parts:
            text = "\n".join(parts)
    if text is None:
        return None, "transcript: no assistant text after the last user event"
    return text, "transcript"


def stop_line(text):
    """('YOURS', n) or ('BLOCKED', n) when the last non-blank line declares a
    stop; trailing white space, backticks and a closing fence are ignored."""
    if not text:
        return None
    rows = [r.strip() for r in text.splitlines()]
    while rows and (not rows[-1] or re.fullmatch(r"`{3,}|~{3,}", rows[-1])):
        rows.pop()
    if not rows:
        return None
    last = rows[-1].strip("`").strip()
    m = YOURS_RE.fullmatch(last)
    if m:
        return "YOURS", int(m.group(1))
    m = BLOCKED_RE.fullmatch(last)
    if m:
        return "BLOCKED", int(m.group(1))
    return None


def _open_items(dl):
    """The open items: every POINTABLE not DONE and every malformed line."""
    out, _, _, _ = evaluate(dl)  # one printed line per item, in order
    lines, nums = [], []
    for x, printed in zip(dl.items(), out):
        if x.tag == "MALFORMED" or (x.tag == "POINTABLE" and x.state != "DONE"):
            lines.append(printed)
            nums.append(x.label)
    return lines, nums


def _reason(open_lines, k, cap):
    head = (f"done-list: {len(open_lines)} item(s) open: " + "; ".join(open_lines)
            + f". This is continuation {k} of {cap}.")
    if k >= cap:
        tail = (" It is the last: write each open item as NOT DONE in your report,"
                " then stop with one of the two stop lines.")
    else:
        tail = " Work the open items, or end your message with one of the two stop lines."
    return (head + tail + " The stop lines, each the last line of your message:"
            " STOP: YOURS #n (the next item is the person's), or"
            " STOP: BLOCKED #n: <what blocks it>.")


def cmd_hook(args):
    state = _state_dir(args)
    raw = sys.stdin.read()
    entry = {"time": _now(), "session_id": None, "event": None, "step": "fired",
             "action": None, "open": [], "stop_hook_active": None, "note": ""}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        data, entry["note"] = None, f"input is not JSON ({type(exc).__name__})"
    if data is not None:
        entry.update(session_id=data.get("session_id"), event=data.get("hook_event_name"),
                     stop_hook_active=data.get("stop_hook_active"))
    try:
        _log(state, entry)
    except OSError as exc:
        print(f"done-list hook: allowed; its log could not be written"
              f" ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 0
    session = entry["session_id"]

    def acted(action, open_=(), note=""):
        done = dict(entry, time=_now(), step="acted", action=action, open=list(open_),
                    note=note)
        try:
            _log(state, done)
        except OSError as exc:
            print(f"done-list hook: its acted line could not be written"
                  f" ({type(exc).__name__}: {exc})", file=sys.stderr)

    try:
        if data is None:
            acted("error", note=entry["note"])
            return 0
        if entry["event"] != "Stop":
            acted("ignored", note=f"not a Stop event: {entry['event']}; counter untouched")
            return 0
        try:
            dl = DoneList(args.list)
        except NotAList as exc:
            dl, not_list = None, str(exc)
        except OSError as exc:
            _set_blocks(state, session, 0)
            acted("unreadable", note=f"the list could not be opened ({type(exc).__name__})")
            return 0
        text, how = last_message(data)
        declared = stop_line(text)
        if declared:
            kind, num = declared
            note = f"STOP: {kind} #{num} ({how})"
            if kind == "YOURS":
                item = dl.item(num) if dl else None
                if dl is None:
                    note += "; the file is not a list, so the item cannot be read"
                elif item is None:
                    note += f"; no item #{num} in the list"
                elif item.tag not in ("YOURS", "WITNESSED"):
                    note += f"; item #{num} is tagged {item.tag}, not YOURS"
            _set_blocks(state, session, 0)
            acted("declared", note=note)
            return 0
        if dl is None:
            open_lines, nums = [f"not a list: {not_list}"], ["list"]
            cap = CAP_DEFAULT
        else:
            open_lines, nums = _open_items(dl)
            cap = dl.cap
        if not open_lines:
            _set_blocks(state, session, 0)
            acted("done", note=f"every POINTABLE exits 0 ({how})")
            return 0
        k = _blocks(state, session) + 1
        if k > cap:
            _set_blocks(state, session, 0)
            acted("cap", nums, note=f"cap {cap} reached; allowed with items open")
            return 0
        _set_blocks(state, session, k)
        acted("block", nums, note=f"continuation {k} of {cap} ({how})")
        print(json.dumps({"decision": "block", "reason": _reason(open_lines, k, cap)}))
        return 0
    except Exception as exc:  # fail-open: a hook that blocks on its own error traps the session
        acted("error", note=f"the hook erred ({type(exc).__name__}: {exc})")
        print(f"done-list hook: allowed on its own error ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return 0


# ---------------------------------------------------------------- report

def cmd_report(args):
    path = os.path.join(_state_dir(args), "log.jsonl")
    entries, unreadable = [], 0
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    e = json.loads(raw)
                    if not isinstance(e, dict) or e.get("step") not in ("fired", "acted"):
                        raise ValueError
                    entries.append(e)
                except ValueError:
                    unreadable += 1
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"hook log could not be read ({type(exc).__name__}): can't tell")
        return 2
    fires = [e for e in entries if e["step"] == "fired"]
    if not fires:
        print("hook never fired: can't tell (an empty log is not a clean run;"
              " it may never have been armed, or never reached)")
        if unreadable:
            print(f"unreadable log lines: {unreadable}")
        return 2
    pending, killed = {}, 0
    actions = {}
    for e in entries:
        key = e.get("session_id")
        if e["step"] == "fired":
            if pending.get(key):
                killed += 1
            pending[key] = True
        else:
            pending[key] = False
            actions[e.get("action")] = actions.get(e.get("action"), 0) + 1
    killed += sum(1 for v in pending.values() if v)
    print(f"fires: {len(fires)} · killed: {killed} · continuations: {actions.get('block', 0)}"
          f" · cap hits: {actions.get('cap', 0)} · declared stops: {actions.get('declared', 0)}"
          f" · allowed on error: {actions.get('error', 0)}")
    print(f"other allows: done {actions.get('done', 0)} · not a Stop event"
          f" {actions.get('ignored', 0)} · list could not be opened"
          f" {actions.get('unreadable', 0)}" + (f" · unreadable log lines {unreadable}"
                                                if unreadable else ""))
    for e in entries:
        if e["step"] == "acted":
            opens = ",".join(str(o) for o in e.get("open") or []) or "-"
            print(f"{e.get('time')} · {e.get('event')} · {e.get('action')} · open {opens}"
                  f" · stop_hook_active {e.get('stop_hook_active')} · {e.get('note')}")
    if killed:
        print("killed: a fired line with no acted line after it (the harness ended the"
              " hook, or a fire was still running when this report read the log)")
    return 0


# ---------------------------------------------------------------- self-test

TESTS = os.path.join(HERE, "tests")


def _selftest(no_log):
    results = []

    def expect(label, ok, shown=""):
        results.append(bool(ok))
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f" -> {shown}" if shown else ""))

    def run(argv, stdin=None):
        p = subprocess.run([sys.executable, os.path.abspath(__file__), *argv],
                           input=stdin, capture_output=True, text=True, cwd=TESTS,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return p.returncode, p.stdout, p.stderr

    def fx(name):
        hits = sorted(f for f in os.listdir(TESTS) if name in f)
        return hits[0]

    with open(os.path.join(TESTS, "check-cases.json"), encoding="utf-8") as fh:
        check_cases = json.load(fh)
    print("== check: one line per item, three states")
    for case in check_cases:
        argv = ["check", case["list"], "--no-log"] + (["--before-work"] if case.get("before_work") else [])
        code, out, _ = run(argv)
        print(f"-- {case['label']} ({case['list']})")
        for line in out.splitlines():
            if not line.startswith(("read:", "logged:")):
                print("   " + line)
        missing = [w for w in case["expect"] if w not in out]
        absent_ok = not [w for w in case.get("absent", []) if w in out]
        expect(f"{case['label']}: exit {case['exit']}", code == case["exit"] and not missing
               and absent_ok, f"exit {code}" + (f", missing {missing}" if missing else ""))

    if shutil.which("pgrep"):  # the timeout fixture's command is `sleep 4711 & sleep 4711`
        left = subprocess.run(["pgrep", "-f", "sleep 4711"], capture_output=True).returncode
        expect("a timeout ends the command's whole process group (no sleep 4711 left)", left == 1)
    else:
        print("can't tell whether the timeout ended the whole process group: no pgrep here")

    with open(os.path.join(TESTS, "hook-cases.json"), encoding="utf-8") as fh:
        hook_cases = json.load(fh)
    print("== hook: allow, block, cap, fail-open (JSON piped in, state in scratch)")
    with tempfile.TemporaryDirectory() as tmp:
        for case in hook_cases:
            state = os.path.join(tmp, case.get("state", case["label"].split(":")[0]))
            if case.get("state_is_file"):
                with open(state, "w") as fh:
                    fh.write("a file where the state folder would go\n")
            print(f"-- {case['label']} (list {case['list']})")
            for i, inp in enumerate(case["inputs"]):
                with open(os.path.join(TESTS, inp), encoding="utf-8") as fh:
                    stdin = fh.read()
                try:
                    data = json.loads(stdin)
                    if isinstance(data, dict) and isinstance(data.get("transcript_path"), str):
                        data["transcript_path"] = os.path.join(TESTS, data["transcript_path"])
                        stdin = json.dumps(data)
                except ValueError:
                    pass
                lst = os.path.join(TESTS, case["list"])
                code, out, err = run(["hook", "--list", lst, "--state", state], stdin)
                want = case["expect"][i]
                if want == "block":
                    try:
                        d = json.loads(out)
                        ok = d.get("decision") == "block"
                        reason = d.get("reason", "")
                    except ValueError:
                        ok, reason = False, out
                    need = case.get("reason_has", [])
                    need = need[i] if need and isinstance(need[0], list) else need
                    miss = [w for w in need if w not in reason]
                    print(f"   input {inp}: block · {reason[:150]}")
                    expect(f"{case['label']} [{i + 1}] block", code == 0 and ok and not miss,
                           f"missing {miss}" if miss else "")
                else:
                    print(f"   input {inp}: allow (exit {code}, stdout {'empty' if not out else 'NOT empty'})")
                    expect(f"{case['label']} [{i + 1}] allow", code == 0 and out == "")
                if case.get("stderr_has") and i == len(case["inputs"]) - 1:
                    expect(f"{case['label']}: the error on standard error",
                           case["stderr_has"] in err)  # its text names a scratch path
            log = os.path.join(state, "log.jsonl")
            if case.get("log_has") or case.get("counter"):
                try:
                    with open(log, encoding="utf-8") as fh:
                        lines = [json.loads(r) for r in fh if r.strip()]
                except OSError:
                    lines = []
                acted = [e for e in lines if e["step"] == "acted"]
                fired = [e for e in lines if e["step"] == "fired"]
                for word in case.get("log_has", []):
                    hit = any(word in json.dumps(e) for e in acted)
                    expect(f"{case['label']}: logged '{word}'", hit and len(fired) == len(acted))
            if "counter" in case:
                files = [f for f in os.listdir(state) if f != "log.jsonl"] if os.path.isdir(state) else []
                if case["counter"] is None:
                    expect(f"{case['label']}: counter untouched", not files, ",".join(files))
                else:
                    try:
                        with open(os.path.join(state, files[0]), encoding="utf-8") as fh:
                            k = json.load(fh)["blocks"]
                    except (IndexError, OSError, ValueError, KeyError):
                        k = "no readable counter file"
                    expect(f"{case['label']}: counter reads {case['counter']}", k == case["counter"],
                           str(k))
        print("== report: the hook's own log")
        code, out, _ = run(["report", os.path.join(TESTS, fx("open-items")), "--state",
                            os.path.join(tmp, "cap")])
        for line in out.splitlines()[:2]:
            print("   " + line)
        expect("report counts the cap run", code == 0 and "continuations: 4" in out
               and "cap hits: 1" in out and "killed: 0" in out)
        killed = os.path.join(tmp, "killed")
        os.makedirs(killed)
        with open(os.path.join(killed, "log.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": "t", "session_id": "s", "event": "Stop", "step": "fired",
                                 "action": None, "open": [], "stop_hook_active": False,
                                 "note": ""}) + "\n")
        code, out, _ = run(["report", "x.md", "--state", killed])
        print("   " + out.splitlines()[0])
        expect("report counts a fired line with no acted line as killed", "killed: 1" in out)
        code, out, _ = run(["report", "x.md", "--state", os.path.join(tmp, "never")])
        print("   " + out.splitlines()[0])
        expect("report on an empty log: hook never fired, can't tell (the blind twin)",
               code == 2 and "never fired" in out)

    print("== card flags")
    code, out, _ = run(["--earned-by"])
    expect("--earned-by prints the failure that earned it", out.strip() == EARNED_BY)
    code, out, _ = run(["--files"])
    expect("--files prints the tool's own files", out.split() == FILES)

    passed, failed = sum(results), len(results) - sum(results)
    print(f"cases: {len(results)} · passed {passed} · failed {failed}")
    if not no_log:
        path = runlog.write(TOOL, FILES, "planted", "selftest", "selftest", ["fixture"],
                            ["fixture"], {"passed": passed, "failed": failed}, [], [])
        print(f"logged: {os.path.relpath(path)}")
    print("selftest: PASS" if failed == 0 and results else "selftest: FAIL")
    return 0 if failed == 0 and results else 1


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="done_list.py", description=__doc__.split("\n\n")[0],
        epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="run the self-test on its fixtures")
    parser.add_argument("--no-log", action="store_true", help="write no row in runs/")
    parser.add_argument("--files", action="store_true", help="print the tool's own files")
    parser.add_argument("--earned-by", action="store_true", help="print the failure that earned it")
    parser.add_argument("--catching", action="store_true",
                        help="print the outcome names of a half that cannot catch (none here)")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("check", help="run a list: one line per item, three states")
    p.add_argument("list")
    p.add_argument("--before-work", action="store_true",
                   help="a POINTABLE already DONE without [before-work ok] is a catch")
    p.add_argument("--planted", metavar="NOTE", help="log the run as planted, with this note")
    p.add_argument("--no-log", action="store_true", help="write no row")
    p = sub.add_parser("hook", help="the Stop hook: reads the hook's JSON on standard input")
    p.add_argument("--list", required=True)
    p.add_argument("--state", help="the folder for the counter and log (default .done-list/ beside the list)")
    p = sub.add_parser("report", help="print the hook's own log")
    p.add_argument("list")
    p.add_argument("--state")
    argv = sys.argv[1:] if argv is None else argv
    as_hook = bool(argv) and argv[0] == "hook"
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if as_hook and exc.code:  # exit 2 from a Stop hook would block: fail open
            print("done-list hook: allowed; its arguments could not be read", file=sys.stderr)
            return 0
        raise
    if args.files:
        print("\n".join(FILES))
        return 0
    if args.earned_by:
        print(EARNED_BY)
        return 0
    if args.catching:
        return 0
    if args.selftest:
        return _selftest(args.no_log)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "hook":
        try:
            return cmd_hook(args)
        except Exception as exc:  # fail-open, past every guard inside it
            print(f"done-list hook: allowed on its own error ({type(exc).__name__})",
                  file=sys.stderr)
            return 0
    if args.cmd == "report":
        return cmd_report(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
