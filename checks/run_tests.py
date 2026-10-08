#!/usr/bin/env python3
"""run_tests · finds every self-test in the tree, runs each, and proves the tree is left alone.

What it compares: each test's exit code against its last line (`selftest: PASS` or
`selftest: FAIL`); every fixtures folder against the tests found; the tree's state (`git
status --porcelain --ignored --untracked-files=all`) and a fingerprint of the hooks folder
(`git rev-parse --git-path hooks`: names, sizes, modes, hashes) before the run against after it.
How it is fired: on every push and pull request by .github/workflows/checks.yml, and by hand,
`python3 checks/run_tests.py`. A test is a tracked file at checks/<name>.py, tools/<name>.py,
tools/<id>/<main>.py or render.py whose text holds the flag --selftest (nothing under a tests/
folder is a test). Each runs as `python3 <file> --selftest --no-log` from the repository root
with PYTHONDONTWRITEBYTECODE=1, at most 300 seconds.
The failure that earned it: a list of tests kept by hand beside the tests drifts, and the drift
is a test that nothing runs, the most repeated gap in the owner's earlier work.
Its twin: zero tests found is RED. The runner always finds itself, so on the real tree the twin
cannot fire; the blindness that can is a test the pattern missed, so a fixtures folder in any of
three shapes (checks/tests/<name>/ for checks/<name>.py, tools/<id>/tests/ for a main file in
tools/<id>/, tools/tests/<name>/ for tools/<name>.py) with no test found is RED, naming it.
What it does not prove: that a test tests the right thing (each one's fixtures and reviewers do
that). A write into a path that was already dirty before the run is not seen; the line says how
many paths were dirty. Paths with a part named exactly __pycache__ are left out of the comparison,
since an import may write them whatever a test does. Of .git/, only the hooks folder is watched;
the rest of it is not. An edit to a file marked skip-worktree is not seen (git status hides it).
A crash is a non-zero exit whose standard error ends in a traceback: after the last traceback
header every line is indented except the last, the exception line. A crash whose exception
message spans lines, or carries a note, ends in more than one unindented line; standard error
cannot tell that from a line printed after a handled traceback, so it reads by its exit code
(FAIL on exit 1, red either way).

One line per test: `PASS · <file>`, `FAIL · <file> · <last line>` or `CAN'T TELL · <file> · <why>`
(exit 2 or any other code, a crash, a timeout, no output, or a last line that disagrees with the
exit code); then `ran n · passed n · failed n · can't tell n`. Exit 1 if any failed, a fixtures
folder has no test, the tree changed, or no test was found; else 2 if any can't tell; else 0.
  run_tests.py [--root DIR]    DIR defaults to the folder above checks/
  run_tests.py --selftest      fixture tests from checks/tests/run_tests/, in scratch trees
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 300
PATTERNS = [re.compile(p) for p in (r"^checks/[^/]+\.py$", r"^tools/[^/]+\.py$",
                                    r"^tools/[^/]+/[^/]+\.py$", r"^render\.py$")]


class CantTell(Exception):
    pass


def git(root, *args):
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off"] + list(args), cwd=root,
                           capture_output=True, text=True)
    except OSError as e:
        raise CantTell(f"git could not run: {e}")
    if p.returncode != 0:
        err = p.stderr.strip().splitlines()
        raise CantTell(f"git {args[0]} exited {p.returncode}: {err[-1] if err else 'no message'}")
    return p.stdout


def discover(root, tracked):
    tests = []
    for f in sorted(tracked):
        parts = f.split("/")
        if "tests" in parts[:-1] or "__pycache__" in parts or not any(p.match(f) for p in PATTERNS):
            continue
        try:
            with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                if "--selftest" in fh.read():
                    tests.append(f)
        except OSError:
            continue
    return tests


def orphans(tracked, tests):
    """Fixtures folders with no discovered test beside them."""
    folders = set()
    for f in tracked:
        p = f.split("/")
        if len(p) >= 4 and p[0] == "checks" and p[1] == "tests":
            folders.add(("checks/tests/" + p[2] + "/", f"checks/{p[2]}.py"))
        if len(p) >= 4 and p[0] == "tools" and p[1] == "tests":
            folders.add(("tools/tests/" + p[2] + "/", f"tools/{p[2]}.py"))
        elif len(p) >= 4 and p[0] == "tools" and p[2] == "tests":
            folders.add(("tools/" + p[1] + "/tests/", f"tools/{p[1]}/"))
    found = []
    for folder, owner in sorted(folders):
        if owner.endswith(".py"):
            has = owner in tests
        else:
            has = any(t.startswith(owner) and t.count("/") == 2 for t in tests)
        if not has:
            found.append(folder)
    return found


def status(root):
    """Each path's status line, NUL-separated so a name holding a space is read whole; a path with
    a part named exactly __pycache__ is left out."""
    out = git(root, "status", "--porcelain", "-z", "--ignored", "--untracked-files=all")
    recs, seen, skip = out.split("\0"), set(), False
    for rec in recs:
        if skip:
            skip = False  # the source path of a rename or copy
            continue
        if len(rec) < 4:
            continue
        skip = rec[0] in "RC"
        if "__pycache__" not in rec[3:].split("/"):
            seen.add(rec)
    return seen


def hooks_print(root):
    """Names, sizes and hashes of every file in the hooks folder, which git status cannot see."""
    rel = git(root, "rev-parse", "--git-path", "hooks").strip()
    folder = os.path.join(root, rel)
    seen = set()
    for dirpath, _, names in os.walk(folder):
        for n in names:
            full = os.path.join(dirpath, n)
            try:
                with open(full, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()[:16]
                st = os.lstat(full)
                seen.add((os.path.join(rel, os.path.relpath(full, folder)), st.st_size,
                          oct(st.st_mode & 0o7777), digest))
            except OSError as e:
                raise CantTell(f"could not read {full}: {e.strerror}")
    return seen


def ends_in_traceback(stderr):
    """True when standard error ends in a traceback: after the last traceback header, every line
    is indented except the last, the exception line."""
    lines = [l for l in stderr.rstrip().splitlines() if l.strip()]
    heads = [i for i, l in enumerate(lines) if l.startswith("Traceback (most recent call last):")]
    if not heads or heads[-1] == len(lines) - 1:
        return False
    tail = lines[heads[-1] + 1:]
    flush = [i for i, l in enumerate(tail) if not l[:1].isspace()]
    return flush == [len(tail) - 1]


def run_one(root, test):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, test, "--selftest", "--no-log"], cwd=root, env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"CAN'T TELL · {test} · ran past {TIMEOUT} seconds", 2
    except OSError as e:
        return f"CAN'T TELL · {test} · could not run: {e}", 2
    out = [l for l in p.stdout.splitlines() if l.strip()]
    err = p.stderr.strip().splitlines()
    code = p.returncode
    if code != 0 and ends_in_traceback(p.stderr):
        return f"CAN'T TELL · {test} · crashed, exit {code}: {err[-1] if err else ''}", 2
    if not out:
        return f"CAN'T TELL · {test} · printed nothing, exit {code}", 2
    last = out[-1].strip()
    said = {"selftest: PASS": 0, "selftest: FAIL": 1}.get(last)
    if code not in (0, 1):
        return f"CAN'T TELL · {test} · exit {code} · {last}", 2
    if said is not None and said != code:
        return f"CAN'T TELL · {test} · exit {code} disagrees with its last line '{last}'", 2
    note = "" if said is not None else " · last line is not 'selftest: ...', read by the exit code"
    if code == 0:
        return f"PASS · {test}{note}", 0
    return f"FAIL · {test} · {last}{note}", 1


def run(root):
    lines, red, cant = [], False, False
    try:
        tracked = set(git(root, "ls-files", "-z").split("\0")) - {""}
        before = status(root)
        hooks_before = hooks_print(root)
        tests = discover(root, tracked)
        counts = {0: 0, 1: 0, 2: 0}
        for t in tests:
            line, code = run_one(root, t)
            counts[code] += 1
            lines.append(line)
        after = status(root)
        hooks_after = hooks_print(root)
    except CantTell as e:
        return lines + [f"CAN'T TELL · the runner could not look: {e}"], 2
    for folder in orphans(tracked, tests):
        lines.append(f"RED · {folder} is a fixtures folder with no test found for it")
        red = True
    for change in sorted(after ^ before):
        lines.append(f"RED · the tree changed during the run: {change}")
        red = True
    for path in sorted({h[0] for h in hooks_after ^ hooks_before}):
        lines.append(f"RED · the hooks folder changed during the run: {path}")
        red = True
    if not tests:
        lines.append("RED · no test found: a runner that finds nothing is blind")
        red = True
    dirty = f" · tree dirty before the run: {len(before)} paths" if before else " · tree clean before"
    lines.append(f"ran {len(tests)} · passed {counts[0]} · failed {counts[1]} · can't tell"
                 f" {counts[2]}{dirty} · __pycache__/ left out of the tree comparison · hooks folder"
                 f" watched, the rest of .git/ not")
    red = red or counts[1] > 0
    cant = counts[2] > 0
    return lines, (1 if red else 2 if cant else 0)


# ---------------------------------------------------------------- self-test

def selftest():
    fix = os.path.join(HERE, "tests", "run_tests")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    ident = ["-c", "user.name=Self Test", "-c", "user.email=selftest@example.invalid"]
    base = tempfile.mkdtemp(prefix="run-tests-selftest-")

    def tree(case, files):
        """A scratch repository holding the given fixtures at the given places, committed."""
        root = os.path.join(base, case)
        later = {d: s for d, s in files.items() if d.startswith(".git/")}  # after init, mode 644
        files = {d: s for d, s in files.items() if d not in later}
        for dest, src in files.items():
            os.makedirs(os.path.dirname(os.path.join(root, dest)) or root, exist_ok=True)
            shutil.copyfile(os.path.join(fix, src), os.path.join(root, dest))
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "case"]):
            p = subprocess.run(["git"] + ident + args, cwd=root, env=env, capture_output=True)
            if p.returncode != 0:
                raise RuntimeError(f"scratch git {args[0]}: {p.stderr!r}")
        for dest, src in later.items():
            os.makedirs(os.path.dirname(os.path.join(root, dest)), exist_ok=True)
            shutil.copyfile(os.path.join(fix, src), os.path.join(root, dest))
            os.chmod(os.path.join(root, dest), 0o644)
        return root

    one = lambda src: {"checks/case.py": src}
    cases = [  # (label, files, exit wanted, text the output must hold)
        ("a passing test: control-pass.py", one("control-pass.py"), 0, "PASS · checks/case.py"),
        ("a last line of another shape: control-other-shape.py", one("control-other-shape.py"), 0,
         "read by the exit code"),
        ("a failing test: plant-fail.py", one("plant-fail.py"), 1, "FAIL · checks/case.py"),
        ("a crash with exit 1: plant-crash.py", one("plant-crash.py"), 2, "crashed, exit 1"),
        ("a crash whose exception carries a note, read by its exit code: plant-crash-with-note.py",
         one("plant-crash-with-note.py"), 1, "FAIL · checks/case.py · fixture case: about to break"),
        ("a test that arms a dormant hook: plant-arms-hook.py",
         {"checks/case.py": "plant-arms-hook.py", ".git/hooks/pre-push": "plant-dormant-hook.txt"},
         1, "the hooks folder changed during the run: .git/hooks/pre-push"),
        ("a write into 'FIXTURE __pycache__/': plant-spaced-pycache.py",
         one("plant-spaced-pycache.py"), 1, "FIXTURE __pycache__/left.txt"),
        ("a named limit, a skip-worktree edit unseen: control-skip-worktree.py",
         {"checks/case.py": "control-skip-worktree.py", "notes.txt": "control-skip-worktree-notes.txt"},
         0, "PASS · checks/case.py"),
        ("a handled traceback, then an honest FAIL: plant-handled-traceback.py",
         one("plant-handled-traceback.py"), 1, "FAIL · checks/case.py · selftest: FAIL"),
        ("a test that installs a hook: plant-installs-hook.py", one("plant-installs-hook.py"), 1,
         "the hooks folder changed during the run: .git/hooks/pre-push"),
        ("a write into notes__pycache__/: plant-pycache-lookalike.py",
         one("plant-pycache-lookalike.py"), 1, "?? notes__pycache__/left.txt"),
        ("a death on a signal: plant-signal.py", one("plant-signal.py"), 2, "CAN'T TELL · checks/case.py"),
        ("a silent test: plant-silent.py", one("plant-silent.py"), 2, "printed nothing"),
        ("exit 0, last line FAIL: plant-disagree.py", one("plant-disagree.py"), 2, "disagrees"),
        ("a test that writes a file: plant-writes.py", one("plant-writes.py"), 1,
         "the tree changed during the run: ?? written-by-a-test.txt"),
        ("a test that writes into an ignored folder: plant-writes-ignored.py",
         {"checks/case.py": "plant-writes-ignored.py", ".gitignore": "plant-ignore-rules.txt"}, 1,
         "the tree changed during the run: !! state/run.json"),
        ("a fixtures folder with no test: plant-orphan-fixture.txt",
         {"checks/case.py": "control-pass.py", "checks/tests/lonely/a.txt": "plant-orphan-fixture.txt",
          "tools/demo/tests/a.txt": "plant-orphan-fixture.txt",
          "tools/tests/lonely/a.txt": "plant-orphan-fixture.txt"}, 1,
         "checks/tests/lonely/ is a fixtures folder with no test"),
        ("zero tests, a helper without the flag (the twin): twin-helper.py",
         {"checks/helper.py": "twin-helper.py"}, 1, "no test found"),
    ]
    ok_all = True
    try:
        for i, (label, files, want, text) in enumerate(cases):
            lines, code = run(tree(f"case{i}", files))
            joined = "\n".join(lines)
            ok = code == want and text in joined
            if "fixtures folder" in label:
                ok = (ok and "tools/demo/tests/ is a fixtures folder with no test" in joined
                      and "tools/tests/lonely/ is a fixtures folder with no test" in joined)
            ok_all &= ok
            shown = next((l for l in lines if text in l), lines[0] if lines else "(no line)")
            print(f"{'ok  ' if ok else 'FAIL'} · {label} · want {want}, got {code} · {shown}")
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
        print(f"CAN'T TELL · unknown arguments {' '.join(args)}; see --help")
        return 2
    lines, code = run(root)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
