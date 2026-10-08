#!/usr/bin/env python3
"""runlog: the shared run-log writer and reader. Every row says planted or real.

How it is fired: imported by every tool that logs a run (write), and by the
renderer for a card's "what it has caught" line (caught_line). Its own self-test
is fired by hand or by the test runner: python3 tools/runlog.py --selftest.

The failure that earned it: logs that could not tell a planted test run from a
real one, so "has this ever caught something real?" had no answer in the log.

Shape (SPEC-run-log.md): folder runs/, one JSON file per run, named
<UTC YYYYMMDDTHHMMSS.ffffffZ>_<tool id>_<kind>.json, one key per line.
Python 3.11 or later, standard library only, plus git.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

KINDS = ("planted", "real")
INVOKERS = ("selftest", "person")
FIELDS = ("tool", "started", "kind", "planted_by", "invoked_by", "read",
          "compared_against", "outcomes", "caught", "could_not", "tool_version")
NAME_RE = re.compile(r"^(\d{8}T\d{6}\.\d{6}Z)_([^_]+)_([^_]+)\.json$")


class RunLogError(ValueError):
    """A row the writer refuses to write."""


class BadKind(RunLogError):
    """kind is neither planted nor real."""


class UnnamedPlant(RunLogError):
    """A planted row with an empty planted_by."""


class SelftestWroteReal(RunLogError):
    """A real row whose invoked_by is selftest."""


class RealReadFixture(RunLogError):
    """A real row whose read or compared_against names fixture material."""


# ---------------------------------------------------------------- locations

def _git(args, cwd):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_root(path):
    """The top folder of the git repository holding path, or None."""
    folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    top = _git(["rev-parse", "--show-toplevel"], folder)
    return os.path.realpath(top) if top else None


def _anchor(files):
    """The tool's own file, made absolute; this module's file when none is given."""
    return os.path.abspath(files[0]) if files else os.path.abspath(__file__)


def default_folder(files=None):
    """runs/ under the root of the repository holding the tool's own file;
    under the working folder when that file is in no repository."""
    root = repo_root(_anchor(files))
    return os.path.join(root if root else os.getcwd(), "runs")


def tool_version(files):
    """The full id of the latest commit touching files, '+dirty' when they have
    uncommitted changes, 'uncommitted' when none is committed, 'no git' otherwise."""
    anchor = _anchor(files)
    root = repo_root(anchor)
    if root is None:
        return "no git"
    paths = [os.path.relpath(os.path.realpath(os.path.abspath(f)), root)
             for f in (files or [anchor])]
    last = _git(["log", "-1", "--format=%H", "--", *paths], root)
    if last is None:
        return "no git"
    if not last:
        return "uncommitted"
    dirty = _git(["status", "--porcelain", "--", *paths], root)
    return last + "+dirty" if dirty else last


# ---------------------------------------------------------------- writer

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(v) for v in value]


def _names_fixture(entry):
    if entry.strip().lower() == "fixture":
        return True
    parts = re.split(r"[\\/]+", os.path.normpath(entry.replace("\\", "/")))
    return "tests" in parts


def write(tool, files, kind, planted_by, invoked_by, read, compared_against,
          outcomes, caught, could_not, folder=None):
    """Write one run row and return its path. Refuses a bad row with a named error."""
    if kind not in KINDS:
        raise BadKind(f"kind must be planted or real, not {kind!r}")
    if invoked_by not in INVOKERS:
        raise RunLogError(f"invoked_by must be selftest or person, not {invoked_by!r}")
    planted_by = (planted_by or "").strip()
    if kind == "planted" and not planted_by:
        raise UnnamedPlant("a planted row must say what was planted and by whom")
    if kind == "real" and planted_by:
        raise RunLogError("a real row carries no planted_by")
    if kind == "real" and invoked_by == "selftest":
        raise SelftestWroteReal("a self-test writes planted rows only")
    read, compared_against = _as_list(read), _as_list(compared_against)
    if kind == "real":
        bad = [e for e in read + compared_against if _names_fixture(e)]
        if bad:
            raise RealReadFixture(f"a real row read fixture material: {bad[0]}")
    if not tool or "_" in tool:
        raise RunLogError(f"a tool id is non-empty and carries no underscore: {tool!r}")
    if not isinstance(outcomes, dict):
        raise RunLogError("outcomes is a map of outcome name to count")
    folder = folder or default_folder(files)
    os.makedirs(folder, exist_ok=True)
    row = {
        "tool": tool, "started": None, "kind": kind, "planted_by": planted_by,
        "invoked_by": invoked_by, "read": read, "compared_against": compared_against,
        "outcomes": {str(k): v for k, v in outcomes.items()},
        "caught": _as_list(caught), "could_not": _as_list(could_not),
        "tool_version": tool_version(files),
    }
    now = datetime.datetime.now(datetime.timezone.utc)
    while True:  # two runs in one microsecond still leave two files
        stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
        row["started"] = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        path = os.path.join(folder, f"{stamp}_{tool}_{kind}.json")
        try:
            with open(path, "x", encoding="utf-8") as fh:
                fh.write(json.dumps(row, indent=2, ensure_ascii=False) + "\n")
            return path
        except FileExistsError:
            now += datetime.timedelta(microseconds=1)


# ---------------------------------------------------------------- reader

class Rows(list):
    """Readable rows, newest first; .cant_tell lists (file name, reason) pairs."""

    def __init__(self, rows=(), cant_tell=()):
        super().__init__(rows)
        self.cant_tell = list(cant_tell)


def _parse_time(text):
    if not isinstance(text, str) or not text.endswith("Z"):
        return None
    try:
        return datetime.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        return None


def _check_row(row, name_tool, name_kind):
    if not isinstance(row, dict):
        return "not a JSON object"
    if "kind" not in row:
        return "no kind"
    if row["kind"] not in KINDS:
        return f"kind is {row['kind']!r}"
    missing = [f for f in FIELDS if f not in row]
    if missing:
        return "missing " + ", ".join(missing)
    if row["kind"] != name_kind:
        return f"name says {name_kind}, field says {row['kind']}"
    if row["tool"] != name_tool:
        return f"name says {name_tool}, field says {row['tool']}"
    if _parse_time(row["started"]) is None:
        return "started is not a UTC time"
    if not isinstance(row["outcomes"], dict):
        return "outcomes is not a map"
    for f in ("caught", "could_not", "read", "compared_against"):
        if not isinstance(row[f], list):
            return f"{f} is not a list"
    return None


def rows(tool, folder=None):
    """The folder's rows for tool, newest first by started. Malformed files are
    in .cant_tell; a .json whose name does not parse is listed for every tool."""
    folder = folder or default_folder()
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return Rows()
    good, bad = [], []
    for name in names:
        if not name.endswith(".json"):
            continue
        m = NAME_RE.match(name)
        if not m:
            bad.append((name, "name does not parse"))
            continue
        if m.group(2) != tool:
            continue
        if m.group(3) not in KINDS:
            bad.append((name, f"name says kind {m.group(3)!r}"))
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                row = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            bad.append((name, f"not readable JSON ({type(exc).__name__})"))
            continue
        reason = _check_row(row, m.group(2), m.group(3))
        if reason:
            bad.append((name, reason))
            continue
        row = dict(row)
        row["_file"] = name
        good.append(row)
    good.sort(key=lambda r: _parse_time(r["started"]), reverse=True)
    return Rows(good, bad)


def _plural(n, one, many):
    return f"{n} {one}" if n == 1 else f"{n} {many}"


def caught_line(tool, catching=None, folder=None):
    """The card's "what it has caught" sentence, from the tool's real rows only."""
    found = rows(tool, folder)
    unreadable = len(found.cant_tell)
    checking, other = [], []
    for row in found:
        if row["kind"] != "real":
            continue
        keys = set(row["outcomes"])
        if catching is None or keys & set(catching):
            checking.append(row)
        elif keys:
            other.append(row)
        else:
            unreadable += 1
    caught = [(r["started"][:10], line) for r in checking for line in r["caught"]]
    if not checking:
        parts = ["no checking run yet" if other else "no real run yet"]
    elif not caught:
        parts = [_plural(len(checking), "real run", "real runs") + ", nothing caught yet"]
    else:
        lines = [f"{day} {line}" for day, line in caught[:10]]
        if len(caught) > 10:
            lines.append(f"and {len(caught) - 10} more")
        parts = ["; ".join(lines)]
    blind = sum(1 for r in checking if r["could_not"])
    if blind:
        parts.append(_plural(blind, "run could not see everything",
                             "runs could not see everything"))
    if other:
        parts.append(_plural(len(other), "other run", "other runs"))
        other_blind = sum(1 for r in other if r["could_not"])
        if other_blind:
            parts.append(f"{other_blind} of them could not see everything")
    if unreadable:
        parts.append(_plural(unreadable, "run file could not be read",
                             "run files could not be read"))
    return " · ".join(parts)


# ---------------------------------------------------------------- self-test

def _selftest():
    results = []

    def expect(label, ok, shown=""):
        results.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f" -> {shown}" if shown else ""))

    def refuses(label, err, **kw):
        args = dict(tool="fixture-tool", files=[__file__], kind="real", planted_by="",
                    invoked_by="person", read=["a.md"], compared_against=["b.txt"],
                    outcomes={"exact": 1}, caught=[], could_not=[], folder=folder)
        args.update(kw)
        try:
            write(**args)
            expect(label, False, "written")
        except err as exc:
            expect(label, True, f"{type(exc).__name__}")

    T = "fixture-tool"
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "runs")
        base = dict(tool=T, files=[__file__], compared_against=["b.txt"], folder=folder)
        p1 = write(kind="planted", planted_by="selftest", invoked_by="selftest",
                   read=["fixture"], outcomes={"exact": 1}, caught=[], could_not=[], **base)
        p2 = write(kind="real", planted_by="", invoked_by="person", read=["a.md"],
                   outcomes={"exact": 1}, caught=[], could_not=[], **base)
        expect("planted row written", p1.endswith("_fixture-tool_planted.json"),
               os.path.basename(p1)[24:])
        expect("real row written", p2.endswith("_fixture-tool_real.json"),
               os.path.basename(p2)[24:])
        with open(p2, encoding="utf-8") as fh:
            body = fh.read()
        expect("one key per line, every field", all(f'"{f}":' in body for f in FIELDS)
               and body.count("\n") >= len(FIELDS))
        expect("tool_version is set", len(json.loads(body)["tool_version"]) >= 6,
               json.loads(body)["tool_version"][:12])
        a = write(kind="planted", planted_by="selftest", invoked_by="selftest",
                  read=["fixture"], outcomes={}, caught=[], could_not=[], **base)
        b = write(kind="planted", planted_by="selftest", invoked_by="selftest",
                  read=["fixture"], outcomes={}, caught=[], could_not=[], **base)
        expect("two writes in one second leave two files",
               a != b and os.path.exists(a) and os.path.exists(b))
        refuses("refuses kind = test", BadKind, kind="test")
        refuses("refuses a plant with no planted_by", UnnamedPlant,
                kind="planted", planted_by=" ")
        refuses("refuses a real row from a self-test", SelftestWroteReal,
                invoked_by="selftest")
        refuses("refuses a real row reading fixture", RealReadFixture, read=["fixture"])
        refuses("refuses a real row reading a tests path", RealReadFixture,
                compared_against=["tools/x/./tests/words.txt"])
        refuses("refuses a tests path hidden by ..", RealReadFixture,
                read=["tools/tests/../tests/a.md"])
        try:
            write(kind="real", planted_by="", invoked_by="person", read=["contests/a.md"],
                  outcomes={}, caught=[], could_not=[], **base)
            expect("a component merely containing 'tests' is not refused", True)
        except RunLogError as exc:
            expect("a component merely containing 'tests' is not refused", False, str(exc))

    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "runs")
        expect("missing folder gives no rows", rows(T, folder) == [] and
               not rows(T, folder).cant_tell)
        line = caught_line(T, folder=folder)
        expect("blind twin: empty folder", line == "no real run yet", line)
        os.makedirs(folder)

        def put(name, row):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
                fh.write(row if isinstance(row, str) else json.dumps(row))

        def row(kind, started, caught=(), could_not=(), outcomes=None, tool=T):
            return {"tool": tool, "started": started, "kind": kind,
                    "planted_by": "selftest" if kind == "planted" else "",
                    "invoked_by": "person", "read": ["a.md"], "compared_against": [],
                    "outcomes": {"exact": 1} if outcomes is None else outcomes,
                    "caught": list(caught), "could_not": list(could_not),
                    "tool_version": "uncommitted"}

        put("20261001T000000.000000Z_fixture-tool_planted.json",
            row("planted", "2026-10-01T00:00:00.000000Z", caught=["a plant, never a catch"]))
        line = caught_line(T, folder=folder)
        expect("planted rows only", line == "no real run yet", line)
        put("20261002T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-02T00:00:00.000000Z"))
        line = caught_line(T, folder=folder)
        expect("one real row, nothing caught", line == "1 real run, nothing caught yet", line)
        put("20261003T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-03T00:00:00.000000Z", could_not=["words file missing"]))
        line = caught_line(T, folder=folder)
        expect("two real rows, one blind",
               line == "2 real runs, nothing caught yet · 1 run could not see everything", line)
        # name order and started order disagree: started wins
        put("20261004T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-05T00:00:00.000000Z", caught=["quote absent: page:3"]))
        put("20261005T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-04T00:00:00.000000Z", caught=["quote absent: page:9"]))
        got = rows(T, folder)
        expect("rows newest first by started", [r["started"][:10] for r in got] ==
               ["2026-10-05", "2026-10-04", "2026-10-03", "2026-10-02", "2026-10-01"])
        line = caught_line(T, folder=folder)
        expect("caught lines, newest first", line == "2026-10-05 quote absent: page:3; "
               "2026-10-04 quote absent: page:9 · 1 run could not see everything", line)
        put("20261006T000000.000000Z_fixture-tool_real.json", '{"tool": "fixture-tool"}')
        put("20261007T000000.000000Z_fixture-tool_real.json", "not json {")
        put("20261008T000000.000000Z_fixture-tool_real.json",
            row("planted", "2026-10-08T00:00:00.000000Z"))
        put("20261009T000000.000000Z_other-tool_real.json", "ignored: another tool")
        put("notes.txt", "ignored: not .json")
        got = rows(T, folder)
        reasons = dict(got.cant_tell)
        expect("no kind is can't tell",
               reasons.get("20261006T000000.000000Z_fixture-tool_real.json") == "no kind")
        expect("not JSON is can't tell",
               "not readable JSON" in reasons.get("20261007T000000.000000Z_fixture-tool_real.json", ""))
        expect("name real, field planted is can't tell",
               "name says real" in reasons.get("20261008T000000.000000Z_fixture-tool_real.json", ""))
        expect("other tools and non-json ignored", len(got.cant_tell) == 3 and len(got) == 5)
        line = caught_line(T, folder=folder)
        expect("could-not-be-read tail beside good rows",
               line.endswith(" · 3 run files could not be read"), line)
        for i in range(10):
            put(f"2026101{i}T000000.000000Z_fixture-tool_real.json",
                row("real", f"2026-10-1{i}T00:00:00.000000Z", caught=[f"catch {i}"]))
        line = caught_line(T, folder=folder)
        expect("at most ten, then and n more", line.count("catch ") == 10 and
               "; and 2 more" in line and line.startswith("2026-10-19 catch 9"), line[:40] + "…")

    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "runs")
        os.makedirs(folder)
        cat = ["exact", "corrected", "absent", "cant_check"]
        put("20261001T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-01T00:00:00.000000Z", outcomes={"messages": 3}))
        line = caught_line(T, catching=cat, folder=folder)
        expect("only other runs", line == "no checking run yet · 1 other run", line)
        put("20261002T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-02T00:00:00.000000Z", outcomes={"exact": 0, "absent": 0}))
        put("20261003T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-03T00:00:00.000000Z", outcomes={"messages": 0},
                could_not=["record 1:4"]))
        put("20261004T000000.000000Z_fixture-tool_real.json",
            row("real", "2026-10-04T00:00:00.000000Z", outcomes={}))
        line = caught_line(T, catching=cat, folder=folder)
        expect("checking and other runs told apart", line == "1 real run, nothing caught yet"
               " · 2 other runs · 1 of them could not see everything"
               " · 1 run file could not be read", line)

    passed = all(results)
    print(f"{sum(results)}/{len(results)} fixtures")
    print("selftest: PASS" if passed else "selftest: FAIL")
    return 0 if passed else 1


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(__doc__.strip())
        print("\nUsage: python3 tools/runlog.py --selftest [--no-log]"
              "\n--no-log is accepted and ignored: the self-test writes only to a"
              " temporary folder.")
        return 0
    if "--selftest" in argv:
        try:
            return _selftest()
        except Exception as exc:  # a crash is a failure, never a silent end
            print(f"FAIL self-test crashed: {type(exc).__name__}: {exc}")
            print("selftest: FAIL")
            return 1
    print("runlog is a module; run it with --selftest or --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
