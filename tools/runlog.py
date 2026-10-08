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

Import it by its path, never as a package (no folder here is one):
    sys.path.insert(0, "<repository root>/tools"); import runlog

`files` (write, tool_version): the tool's own files. A relative entry is relative
to the root of the repository that holds this module (the card's form); an
absolute entry is used as given (a tool in another repository passes these).
Never resolved against the working folder.

`read` and `compared_against`: paths relative to the repository, `fixture`, or
the phrase "outside the repository"; an absolute path or one climbing out of
the repository is refused (the folder is public; a path into a machine is not).

Refusals, each its own class (all are RunLogError): BadKind · BadInvoker ·
BadToolId (not lower-case letters, digits, hyphens) · UnnamedPlant ·
SelftestWroteReal · RealReadFixture (`fixture`, or a path component `tests` in
any letter case) · ReservedTool (a real row under `fixture-tool` in a tool's log
folder; a self-test's own temporary folder may hold one) · MachinePath ·
RealCarriesPlant (a real row with planted_by) · NotOneLine (a caught or
could_not entry empty or holding a line break) · BadOutcomes (not a non-empty
map of name to whole number).

Limit, said plainly: the module never reads the corpus, so it does not know a
tool's own outcome names. caught_line(tool, catching): a real row carrying a
`catching` key is a checking run; one carrying only other keys is an "other
run"; one with an empty outcomes map, or whose started time is not an ISO 8601
UTC time, is can't tell, counted with the unreadable files. A misspelled key
therefore reads as an other run, never as a catch.
"""

import datetime
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile

KINDS = ("planted", "real")
INVOKERS = ("selftest", "person")
RESERVED = "fixture-tool"
FIELDS = ("tool", "started", "kind", "planted_by", "invoked_by", "read",
          "compared_against", "outcomes", "caught", "could_not", "tool_version")
NAME_RE = re.compile(r"^(\d{8}T\d{6}\.\d{6}Z)_([^_]+)_([^_]+)\.json$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OUTSIDE = "outside the repository"


class RunLogError(ValueError):
    """A row the writer refuses to write."""


class BadKind(RunLogError):
    """kind is neither planted nor real."""


class BadInvoker(RunLogError):
    """invoked_by is neither selftest nor person."""


class BadToolId(RunLogError):
    """A tool id that is not lower-case letters, digits and hyphens."""


class UnnamedPlant(RunLogError):
    """A planted row with an empty planted_by."""


class SelftestWroteReal(RunLogError):
    """A real row whose invoked_by is selftest."""


class RealReadFixture(RunLogError):
    """A real row whose read or compared_against names fixture material."""


class ReservedTool(RunLogError):
    """A real row under the reserved id fixture-tool."""


class MachinePath(RunLogError):
    """A read or compared_against entry that is a path into a machine."""


class RealCarriesPlant(RunLogError):
    """A real row whose planted_by is not empty."""


class NotOneLine(RunLogError):
    """A caught or could_not entry that is empty or holds a line break."""


class BadOutcomes(RunLogError):
    """outcomes is not a non-empty map of outcome name to whole number."""


# ---------------------------------------------------------------- locations

_GIT_MISSING = object()


def _git(args, cwd):
    """git's standard output, None when git refused, _GIT_MISSING when absent."""
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                             text=True, timeout=30)
    except FileNotFoundError:
        return _GIT_MISSING
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_root(path):
    """The top folder of the repository holding path, or None. With no git on
    the machine, the nearest folder above holding a .git entry."""
    folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    top = _git(["rev-parse", "--show-toplevel"], folder)
    if top is _GIT_MISSING:
        here = os.path.realpath(folder)
        while True:
            if os.path.exists(os.path.join(here, ".git")):
                return here
            up = os.path.dirname(here)
            if up == here:
                return None
            here = up
    return os.path.realpath(top) if top else None


def module_root():
    """The root of the repository holding this module; the folder above tools/
    when it is in none."""
    here = os.path.abspath(__file__)
    return repo_root(here) or os.path.dirname(os.path.dirname(here))


def _resolve(entry):
    return entry if os.path.isabs(entry) else os.path.join(module_root(), entry)


def _paths(files):
    return [_resolve(f) for f in files] if files else [os.path.abspath(__file__)]


def default_folder(files=None):
    """runs/ under the root of the repository holding the tool's own file;
    under the working folder when that file is in no repository."""
    root = repo_root(_paths(files)[0])
    return os.path.join(root if root else os.getcwd(), "runs")


def tool_version(files):
    """The full id of the latest commit touching files, '+dirty' when they have
    uncommitted changes, 'uncommitted' when none is committed (an empty history
    included), 'no git' when git is unavailable or the folder is no repository."""
    paths = _paths(files)
    root = repo_root(paths[0])
    if root is None or shutil.which("git") is None:
        return "no git"
    rel = [os.path.relpath(os.path.realpath(p), root) for p in paths]
    if _git(["rev-parse", "--verify", "--quiet", "HEAD"], root) is None:
        return "uncommitted"  # a repository with no commit yet
    last = _git(["log", "-1", "--format=%H", "--", *rel], root)
    if not isinstance(last, str):
        return "no git"
    if not last:
        return "uncommitted"
    dirty = _git(["status", "--porcelain", "--", *rel], root)
    return last + "+dirty" if dirty else last


# ---------------------------------------------------------------- writer

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(v) for v in value]


def _clean(entry):
    return posixpath.normpath(entry.strip().replace("\\", "/"))


def _names_fixture(entry):
    if entry.strip().lower() == "fixture":
        return True
    return "tests" in [p.lower() for p in _clean(entry).split("/")]


def _machine_path(entry):
    raw = entry.strip()
    if raw.lower().startswith(OUTSIDE) or raw.lower() == "fixture":
        return False
    if raw.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", raw):
        return True
    clean = _clean(raw)
    return clean == ".." or clean.startswith("../")


def _clock():
    return datetime.datetime.now(datetime.timezone.utc)


def write(tool, files, kind, planted_by, invoked_by, read, compared_against,
          outcomes, caught, could_not, folder=None):
    """Write one run row and return its path. Refuses a bad row with a named error."""
    if kind not in KINDS:
        raise BadKind(f"kind must be planted or real, not {kind!r}")
    if invoked_by not in INVOKERS:
        raise BadInvoker(f"invoked_by must be selftest or person, not {invoked_by!r}")
    if not isinstance(tool, str) or not ID_RE.match(tool):
        raise BadToolId(f"a tool id is lower-case letters, digits and hyphens: {tool!r}")
    planted_by = (planted_by or "").strip()
    read, compared_against = _as_list(read), _as_list(compared_against)
    if kind == "planted" and not planted_by:
        raise UnnamedPlant("a planted row must say what was planted and by whom")
    if kind == "real" and invoked_by == "selftest":
        raise SelftestWroteReal("a self-test writes planted rows only")
    if kind == "real":
        bad = [e for e in read + compared_against if _names_fixture(e)]
        if bad:
            raise RealReadFixture(f"a real row read fixture material: {bad[0]}")
        log = default_folder(files)
        if tool == RESERVED and os.path.realpath(folder or log) == os.path.realpath(log):
            raise ReservedTool(f"{RESERVED} is reserved for self-tests: no real row"
                               " under it lands in a tool's log folder")
    bad = [e for e in read + compared_against if _machine_path(e)]
    if bad:
        raise MachinePath("read and compared_against name paths in the repository,"
                          " never a path into a machine")
    if kind == "real" and planted_by:
        raise RealCarriesPlant("a real row carries no planted_by")
    caught, could_not = _as_list(caught), _as_list(could_not)
    for entry in caught + could_not:
        if not entry.strip() or "\n" in entry or "\r" in entry:
            raise NotOneLine(f"caught and could_not hold one-line strings: {entry!r}")
    if (not isinstance(outcomes, dict) or not outcomes or not all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0
            for v in outcomes.values())):
        raise BadOutcomes("outcomes is a non-empty map of outcome name to count")
    folder = folder or default_folder(files)
    os.makedirs(folder, exist_ok=True)
    row = {
        "tool": tool, "started": None, "kind": kind, "planted_by": planted_by,
        "invoked_by": invoked_by, "read": read, "compared_against": compared_against,
        "outcomes": {str(k): v for k, v in outcomes.items()},
        "caught": caught, "could_not": could_not, "tool_version": tool_version(files),
    }
    now = _clock()
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


def parse_time(text):
    """An ISO 8601 time at UTC (basic or extended form), else None."""
    if not isinstance(text, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if when.tzinfo is None or when.utcoffset() != datetime.timedelta(0):
        return None
    return when


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
    if parse_time(row["started"]) is None:
        return "started is not an ISO 8601 UTC time"
    if not isinstance(row["outcomes"], dict):
        return "outcomes is not a map"
    if not row["outcomes"]:
        return "outcomes is empty"
    for f in ("caught", "could_not", "read", "compared_against"):
        if not isinstance(row[f], list) or not all(isinstance(e, str) for e in row[f]):
            return f"{f} is not a list of strings"
    return None


def rows(tool, folder=None):
    """The folder's rows for tool, newest first by started. Malformed files are
    in .cant_tell; a .json whose name does not parse is listed for every tool."""
    folder = folder or default_folder()
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return Rows()
    except OSError as exc:
        return Rows((), [(folder, f"folder could not be listed ({type(exc).__name__})")])
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
    good.sort(key=lambda r: parse_time(r["started"]), reverse=True)
    return Rows(good, bad)


def _plural(n, one, many):
    return f"{n} {one}" if n == 1 else f"{n} {many}"


def caught_line(tool, catching=None, folder=None):
    """The card's "what it has caught" sentence, from the tool's real rows only.
    An empty or absent `catching` means every real run is a checking run."""
    found = rows(tool, folder)
    unreadable = len(found.cant_tell)
    checking, other = [], []
    for row in found:
        if row["kind"] != "real":
            continue
        if not catching or set(row["outcomes"]) & set(catching):
            checking.append(row)
        else:
            other.append(row)
    caught = [(parse_time(r["started"]).strftime("%Y-%m-%d"), line)
              for r in checking for line in r["caught"]]
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

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "runlog")


def _selftest():
    import tomllib
    global _clock
    results = []

    def expect(label, ok, shown=""):
        results.append(bool(ok))
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f" -> {shown}" if shown else ""))

    # writer: every planted fault is a case in tests/runlog/writer-cases.json
    with open(os.path.join(FIXTURES, "writer-cases.json"), encoding="utf-8") as fh:
        cases = json.load(fh)
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "runs")
        repo = os.path.join(tmp, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        open(os.path.join(repo, "tool.py"), "w").close()
        for case in cases["cases"]:
            args = dict(cases["base"], files=[__file__], folder=folder)
            args.update(case["set"])
            if args.pop("temp_repo", False):  # the default folder: the repo's runs/
                args.update(files=[os.path.join(repo, "tool.py")], folder=None)
            try:
                path = write(**args)
                got = "written"
            except RunLogError as exc:
                path, got = None, type(exc).__name__
            expect(case["label"], got == case["expect"], got)
            if path and case["expect"] == "written":
                with open(path, encoding="utf-8") as fh:
                    body = fh.read()
                row = json.loads(body)
                expect("  one key per line, every field, name and started agree",
                       all(f'\n  "{f}":' in body for f in FIELDS) and
                       os.path.basename(path)[:23] == re.sub(r"[-:]", "", row["started"]))
        frozen = datetime.datetime(2026, 10, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        saved, _clock = _clock, (lambda: frozen)
        try:
            args = dict(cases["base"], files=[__file__], folder=os.path.join(tmp, "same"))
            a, b = write(**args), write(**args)
        finally:
            _clock = saved
        expect("two writes in one microsecond leave two files",
               a != b and os.path.exists(a) and os.path.exists(b),
               os.path.basename(b)[:23])

    # tool_version and where the log lands
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            land = default_folder(["tools/runlog.py"])
            expect("relative files from another folder land under the tool's repository",
                   land == os.path.join(module_root(), "runs"))
            ver = tool_version(["tools/runlog.py"])
            expect("relative files from another folder read a commit id",
                   re.match(r"^[0-9a-f]{40}(\+dirty)?$", ver) is not None, ver[:12])
        finally:
            os.chdir(here)
        plain = os.path.join(tmp, "plain")
        os.makedirs(plain)
        open(os.path.join(plain, "tool.py"), "w").close()
        expect("a folder in no repository reads no git",
               tool_version([os.path.join(plain, "tool.py")]) == "no git")
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        subprocess.run(["git", "init", "-q", empty], check=True)
        open(os.path.join(empty, "tool.py"), "w").close()
        got = tool_version([os.path.join(empty, "tool.py")])
        expect("a repository with no commit reads uncommitted", got == "uncommitted", got)

    # reader and caught_line: committed folders under tests/runlog/lines/
    lines = os.path.join(FIXTURES, "lines")
    expect("missing folder gives no rows",
           rows(RESERVED, os.path.join(lines, "no-such-folder")) == [])
    for case in sorted(os.listdir(lines)):
        folder = os.path.join(lines, case)
        with open(os.path.join(folder, "expect.toml"), "rb") as fh:
            want = tomllib.load(fh)
        got = rows(RESERVED, folder)
        if "order" in want:
            expect(f"{case}: rows newest first by started",
                   [r["_file"][:8] for r in got] == want["order"],
                   " ".join(r["_file"][:8] for r in got))
        for name, reason in want.get("cant_tell", {}).items():
            expect(f"{case}: {name} is can't tell ({reason})",
                   reason in dict(got.cant_tell).get(name, ""),
                   dict(got.cant_tell).get(name, "read as a row"))
        line = caught_line(RESERVED, catching=want.get("catching"), folder=folder)
        expect(f"{case}: line", line == want["line"], line)

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
