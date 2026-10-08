#!/usr/bin/env python3
"""Check 2 · resolution: every link, path, key and card in the corpus points at something real.

What it compares, over tracked paths only (`git ls-files`, so a link resolves only to a file a
clone would see): every `#term:<id>` link and every link path in any record under manual/
(relative to the repository root) against the tracked files; every released card's `files`
against the tracked files; every tool folder (a folder directly under tools/ holding a .py file;
`tests` and `__pycache__` excepted) against the cards, both ways; every record's keys against the
list for its kind, and its `id` against its file name; and, for released cards, `files`,
`earned_by` and `catching` against what `python3 tools/<id>/<id with underscores>.py` prints for
`--files`, `--earned-by` and `--catching` (hand-kept copies, so one check compares them;
`catching` is required whenever the tool prints a name). Building cards' comparisons are
skipped and counted in the line.
How it is fired: by checks/run_all.py on every push and pull request (the workflow), and by hand,
`python3 checks/resolution.py`. It reports; it never stops work.
The failure that earned it: in the owner's earlier manual a card could point at a heading that
no longer existed, and a hand-kept list of files beside a tool drifted from the tool.
Its twin: a manual/ folder with zero records, or a tools/ folder with tools and no cards, is RED;
a missing manual/ folder is CAN'T TELL (a branch building the checks before the corpus exists).
What it does not prove: that a link points at the right place, that a card's words match its
tool, or that every use of a term is linked. Links with a scheme (https:, mailto:) are counted,
not followed; a link to a folder, or one whose target holds a space or a title, is RED. The only
records left unread are the files directly under manual/tests/ (fixtures), counted in the line.
A released card whose main file is not tracked is RED: its copies are never silently uncompared.
A tool that crashes or warns when asked for its copies is CAN'T TELL; so is any git error.

Output, one line: `GREEN · read ...`, `RED: <record>: <target>` or `CAN'T TELL: <what>`; exit 0/1/2.
  resolution.py [--root DIR]    DIR defaults to the folder above checks/
  resolution.py --selftest      scratch repositories built from checks/tests/resolution/
"""
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
CARD_REQUIRED = {"id", "name", "status", "what", "first", "gotcha", "earned_by"}
CARD_RELEASED = {"files", "verified_against"}
KINDS = {  # kind: (required keys, allowed keys)
    "site": ({"title", "owner", "limit", "rooms"}, {"title", "owner", "limit", "rooms"}),
    "rooms": ({"id", "title", "body"}, {"id", "title", "body"}),
    "terms": ({"id", "term", "body"}, {"id", "term", "body"}),
    "readers": ({"id", "sections"}, {"id", "sections"}),
    "tools": (CARD_REQUIRED, CARD_REQUIRED | CARD_RELEASED | {"catching"}),
}
LINK = re.compile(r"\[[^\]]*\]\(([^)]*)\)")
TERM = re.compile(r"#term:([A-Za-z0-9_-]*)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class CantTell(Exception):
    pass


def git_files(root):
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-z"], cwd=root,
                           capture_output=True, text=True)
    except OSError as e:
        raise CantTell(f"git could not run: {e}")
    if p.returncode != 0 or p.stderr.strip():
        msg = p.stderr.strip().splitlines()
        raise CantTell(f"git ls-files exited {p.returncode}: {msg[-1] if msg else 'no message'}")
    return {f for f in p.stdout.split("\0") if f}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)


def ask_tool(root, main, flag):
    try:
        p = subprocess.run([sys.executable, main, flag], cwd=root, capture_output=True, text=True,
                           timeout=60, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CantTell(f"{main} {flag} could not run: {e.__class__.__name__}")
    err = p.stderr.strip().splitlines()
    if p.returncode != 0:
        raise CantTell(f"{main} {flag} exited {p.returncode}: {err[-1] if err else 'no message'}")
    if err:
        raise CantTell(f"{main} {flag} warned: {err[0]}")
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]


def run(root):
    if not os.path.isdir(os.path.join(root, "manual")):
        return "CAN'T TELL: no manual/ folder on this tree, so no records to resolve", 2
    tracked = git_files(root)
    reds, records, cards, fixtures, links, external, skipped = [], {}, {}, 0, 0, 0, 0
    compared = 0
    for path in sorted(f for f in tracked if f.startswith("manual/") and f.endswith(".toml")):
        parts = path.split("/")
        if len(parts) == 3 and parts[1] == "tests":  # manual/tests/<file>: fixtures, one level only
            fixtures += 1
            continue
        try:
            with open(os.path.join(root, path), "rb") as f:
                records[path] = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            reds.append(f"{path}: does not parse ({e.__class__.__name__})")
    if not records and not reds:
        return f"RED: manual/: the folder holds zero records ({fixtures} fixtures not read)", 1

    def resolves(target):
        target = target.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        norm = posixpath.normpath(target) if target else ""
        return bool(norm) and not norm.startswith("..") and norm in tracked  # a file, never a folder

    for path, rec in records.items():
        parts = path.split("/")
        stem = parts[-1][:-5]
        kind = "site" if path == "manual/site.toml" else (parts[1] if len(parts) == 3 else None)
        if kind not in KINDS:
            reds.append(f"{path}: a record in a folder of no kind")
            continue
        required, allowed = KINDS[kind]
        if kind == "tools" and rec.get("status") == "released":
            required = required | CARD_RELEASED
        missing = sorted(k for k in required if k not in rec
                         or (k in CARD_RELEASED and rec[k] in ("", [])))
        extra = sorted(k for k in rec if k not in allowed)
        if missing:
            reds.append(f"{path}: missing key {missing[0]}")
        if extra:
            reds.append(f"{path}: key {extra[0]} is outside its list")
        if kind != "site" and rec.get("id") != stem:
            reds.append(f"{path}: id {rec.get('id')!r} is not its file name {stem!r}")
        if kind == "readers":
            for s in rec.get("sections", []):
                bad = sorted(set(s) - {"heading", "body"}) if isinstance(s, dict) else ["(not a table)"]
                if bad:
                    reds.append(f"{path}: a section carries {bad[0]}, outside heading and body")
        if kind == "tools":
            cards[stem] = (path, rec)
            if stem == "fixture-tool":
                reds.append(f"{path}: the id fixture-tool is reserved")
            if rec.get("status") not in ("building", "released"):
                reds.append(f"{path}: status {rec.get('status')!r} is neither building nor released")
        for text in strings(rec):
            for target in LINK.findall(text):
                if target.startswith("#term:"):
                    continue  # counted and resolved with the term links below
                links += 1
                if re.search(r"\s", target):
                    reds.append(f"{path}: link ({target}) holds a space or a title, outside the"
                                f" markdown subset")
                elif SCHEME.match(target):
                    external += 1
                elif not resolves(target):
                    reds.append(f"{path}: link {target or '(empty)'} resolves to no tracked file")
            for term in TERM.findall(text):
                links += 1
                if f"manual/terms/{term}.toml" not in tracked:
                    reds.append(f"{path}: #term:{term} has no record manual/terms/{term}.toml")

    folders = set()
    for f in tracked:
        p = f.split("/")
        if len(p) == 3 and p[0] == "tools" and p[2].endswith(".py") and p[1] not in ("tests", "__pycache__"):
            folders.add(p[1])
    if folders and not cards:
        reds.append(f"tools/: {len(folders)} tool folder(s) and no cards")
    for name in sorted(folders - set(cards)):
        reds.append(f"tools/{name}/: a tool folder with no card manual/tools/{name}.toml")
    for name in sorted(set(cards) - folders):
        reds.append(f"{cards[name][0]}: a card with no tool folder tools/{name}/")

    try:
        for name, (path, rec) in sorted(cards.items()):
            if rec.get("status") != "released":
                skipped += 1
                continue
            files = rec.get("files") or []
            gone = [f for f in files if f not in tracked]
            if gone:
                reds.append(f"{path}: files names {gone[0]}, which is not tracked")
            main = f"tools/{name}/{name.replace('-', '_')}.py"
            if main not in tracked:
                reds.append(f"{path}: released, and its main file {main} is not tracked, so its"
                            f" copies cannot be compared")
                continue
            compared += 1
            if sorted(ask_tool(root, main, "--files")) != sorted(files):
                reds.append(f"{path}: files differs from what {main} --files prints")
            if " ".join(ask_tool(root, main, "--earned-by")) != str(rec.get("earned_by", "")).strip():
                reds.append(f"{path}: earned_by differs from what {main} --earned-by prints")
            printed = ask_tool(root, main, "--catching")
            if sorted(printed) != sorted(rec.get("catching", [])):
                what = "is missing" if printed and "catching" not in rec else "differs from what"
                reds.append(f"{path}: catching {what} {main} --catching prints")
    except CantTell as e:
        if reds:
            return f"RED: {reds[0]}; {len(reds) - 1} more; and could not ask a tool: {e}", 1
        return f"CAN'T TELL: {e}", 2
    if reds:
        more = f"; {len(reds) - 1} more" if len(reds) > 1 else ""
        return f"RED: {reds[0]}{more}", 1
    return (f"GREEN · read {len(records)} records, {links} links ({external} with a scheme, not"
            f" followed), {len(folders)} tool folders, {len(cards)} cards · against tracked paths"
            f" (git ls-files) · {compared} released card(s) compared with their tools,"
            f" {skipped} building card(s)' comparisons skipped · {fixtures} fixture record(s)"
            f" directly under manual/tests/ not read"), 0


# ---------------------------------------------------------------- self-test

def selftest():
    fix = os.path.join(HERE, "tests", "resolution")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
    ident = ["-c", "user.name=Self Test", "-c", "user.email=selftest@example.invalid"]
    base = tempfile.mkdtemp(prefix="resolution-selftest-")

    def sg(repo, *args):
        p = subprocess.run(["git"] + ident + list(args), cwd=repo, env=env, capture_output=True,
                           text=True)
        if p.returncode != 0:
            raise RuntimeError(f"scratch git {args[0]}: {p.stderr}")

    def build(case):
        """The control corpus, then the case's overlay: files added or replaced, a name ending
        .REMOVE deletes that file, .UNTRACKED is written but never added, REMOVE-ALL starts empty."""
        repo = os.path.join(base, case)
        overlay = os.path.join(fix, case)
        if case == "control-corpus" or not os.path.exists(os.path.join(overlay, "REMOVE-ALL")):
            shutil.copytree(os.path.join(fix, "control-corpus"), repo)
        else:
            os.makedirs(repo)
        untracked = []
        if case != "control-corpus" and os.path.isdir(overlay):
            for dirpath, _, names in os.walk(overlay):
                for n in names:
                    src = os.path.join(dirpath, n)
                    dst = os.path.join(repo, os.path.relpath(src, overlay))
                    if n == "REMOVE-ALL":
                        continue
                    if n.endswith(".REMOVE"):
                        os.remove(dst[:-7])
                        continue
                    if n.endswith(".UNTRACKED"):
                        untracked.append((src, dst[:-10]))
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(src, dst)
        sg(repo, "init", "-q", "-b", "main")
        sg(repo, "add", "-A")
        sg(repo, "commit", "-q", "-m", "The case")
        for src, dst in untracked:  # on disk after the commit, never added
            shutil.copyfile(src, dst)
        return repo

    reason = {  # each case must fail for its own reason, not another one
        "plant-bare-anchor": "link #below", "plant-card-no-folder": "a card with no tool folder",
        "plant-catching-missing": "catching is missing", "plant-dangling-path": "link PLAN.md",
        "plant-dangling-term": "#term:lane has no record", "plant-earned-by-differs": "earned_by differs",
        "plant-extra-key": "key colour is outside", "plant-files-differ": "files differs",
        "plant-folder-no-card": "a tool folder with no card", "plant-id-mismatch": "id 'built'",
        "plant-missing-key": "missing key term", "plant-no-kind": "folder of no kind",
        "plant-reader-section-key": "a section carries note", "plant-released-missing-file":
        "gone.py, which is not tracked", "plant-reserved-id": "fixture-tool is reserved",
        "plant-unparseable": "does not parse", "plant-untracked-target": "link NOTES.md",
        "twin-empty-manual": "zero records", "twin-tools-no-cards": "tool folder(s) and no cards",
        "cant-tell-tool-crash": "--catching exited 1", "control-corpus": "1 released card(s) compared",
        "plant-main-file-missing": "main file tools/demo/demo.py is not tracked",
        "plant-folder-link": "link tools/ resolves to no tracked file",
        "plant-deep-tests": "manual/rooms/tests/hidden.toml: a record in a folder of no kind",
        "plant-link-with-space": "holds a space or a title",
    }
    cases = [("control-corpus", 0)]
    for name in sorted(os.listdir(fix)):
        if name.startswith("plant-") or name.startswith("twin-"):
            cases.append((name, 1))
        elif name.startswith("cant-tell-"):
            cases.append((name, 2))
    ok_all = True
    try:
        for case, want in cases:
            line, code = run(build(case))
            ok = code == want and reason.get(case, "(no reason written)") in line
            ok_all &= ok
            print(f"{'ok  ' if ok else 'FAIL'} · {case} · want {want}, got {code} · {line}")
        empty = os.path.join(base, "no-manual")
        os.makedirs(empty)
        sg(empty, "init", "-q", "-b", "main")
        line, code = run(empty)
        ok = code == 2
        ok_all &= ok
        print(f"{'ok  ' if ok else 'FAIL'} · no manual/ folder · want 2, got {code} · {line}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"selftest: {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


def main(argv):
    args = [a for a in argv if a != "--no-log"]
    if args[:1] == ["--selftest"]:
        return selftest()
    if args[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    root = os.path.dirname(HERE)
    if args[:1] == ["--root"] and len(args) == 2:
        root = args[1]
    elif args:
        print(f"CAN'T TELL: unknown arguments {' '.join(args)}; see --help")
        return 2
    try:
        line, code = run(root)
    except CantTell as e:
        line, code = f"CAN'T TELL: {e}", 2
    except Exception as e:  # a crash is never green
        line, code = f"CAN'T TELL: the check failed: {e.__class__.__name__}: {e}", 2
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
