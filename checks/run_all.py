#!/usr/bin/env python3
"""run_all · the guard's five checks, from a fixed list, one line each.

What it compares: each check's printed state (its one line, opening GREEN, RED or CAN'T TELL)
against the exit code it gave (0, 1, 2). A check that is missing, crashes, prints nothing, prints
more than one line, or whose line and exit code disagree is CAN'T TELL, never green. Exit 0 is
never trusted alone: anything on standard error with exit 0 is CAN'T TELL, and a line must open
with exactly `GREEN · `, `RED: ` or `CAN'T TELL: ` and say something after it. A traceback
on standard error is a crash only with a non-zero exit and no honest line: a check that prints
its state and exits with it has not crashed.
How it is fired: on every push and pull request by .github/workflows/checks.yml, and by hand,
`python3 checks/run_all.py`. It reports; nothing merges or refuses on it.
The failure that earned it: a correct check that nothing runs, the most repeated gap in the
owner's earlier work; and a runner that reads a crash or an empty answer as a pass.
Its twin: a check file renamed away reads CAN'T TELL for its line, and run_all exits 2.
What it does not prove: that any check is right (each check's own self-test does that), or that
the list is complete: the list is fixed here on purpose, and check 3 is listed before it exists,
so its absence shows as CAN'T TELL rather than as nothing.

The five checks: 1 currency · 2 resolution · 3 derived readers · 4 one screen · 5 private words
(the push scanner's --tree mode). Exit 1 if any line is red, else 2 if any is can't tell, else 0:
red first, because a red is a known fault with a known fix, and a can't tell is a blind spot.
  run_all.py [--root DIR]    DIR defaults to the folder above checks/
  run_all.py --selftest      fixture checks from checks/tests/run_all/, in a scratch tree
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = [  # the fixed list: (number, name, file, arguments)
    (1, "currency", "checks/currency.py", []),
    (2, "resolution", "checks/resolution.py", []),
    (3, "derived readers", "checks/derived_readers.py", []),
    (4, "one screen", "checks/one_screen.py", []),
    (5, "private words", "checks/push_scan.py", ["--tree"]),
]
STATES = {0: "GREEN", 1: "RED", 2: "CAN'T TELL"}
OPENINGS = {"GREEN": "GREEN · ", "RED": "RED: ", "CAN'T TELL": "CAN'T TELL: "}  # exact, nothing looser
TIMEOUT = 300


def one(root, number, name, rel, args):
    tag = f"(check {number}, {name})"
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return f"CAN'T TELL: {rel} not found {tag}", 2
    try:
        p = subprocess.run([sys.executable, path] + args, cwd=root, capture_output=True, text=True,
                           timeout=TIMEOUT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return f"CAN'T TELL: {rel} ran past {TIMEOUT} seconds {tag}", 2
    except OSError as e:
        return f"CAN'T TELL: {rel} could not run: {e} {tag}", 2
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    err = p.stderr.strip().splitlines()
    if p.returncode == 0 and err:
        return f"CAN'T TELL: {rel} exited 0 with standard error: {err[0]} {tag}", 2
    line = lines[0] if len(lines) == 1 else ""
    state = next((s for s, opening in OPENINGS.items()
                  if line.startswith(opening) and line[len(opening):].strip()), None)
    if state is not None and STATES.get(p.returncode) == state:
        return f"{line} {tag}", p.returncode  # its state, printed and exited with: not a crash
    if p.returncode != 0 and "Traceback (most recent call last):" in p.stderr:
        return f"CAN'T TELL: {rel} crashed: {err[-1]} {tag}", 2
    if not lines:
        return f"CAN'T TELL: {rel} printed nothing (exit {p.returncode}) {tag}", 2
    if len(lines) > 1:
        return f"CAN'T TELL: {rel} printed {len(lines)} lines, not one (exit {p.returncode}) {tag}", 2
    if state is None or STATES.get(p.returncode) != state:
        return (f"CAN'T TELL: {rel} printed {state or 'no state'} and exited {p.returncode}:"
                f" they disagree {tag}"), 2
    return f"{line} {tag}", p.returncode


def run(root):
    results = [one(root, *c) for c in CHECKS]
    codes = [c for _, c in results]
    return [l for l, _ in results], (1 if 1 in codes else 2 if 2 in codes else 0)


# ---------------------------------------------------------------- self-test

def selftest():
    fix = os.path.join(HERE, "tests", "run_all")
    base = tempfile.mkdtemp(prefix="run-all-selftest-")

    def tree(case, layout):
        """A scratch tree whose five check files are fixture checks; None leaves one missing."""
        root = os.path.join(base, case)
        os.makedirs(os.path.join(root, "checks"))
        for (_, _, rel, _), src in zip(CHECKS, layout):
            if src:
                shutil.copyfile(os.path.join(fix, src), os.path.join(root, rel))
        return root

    g = "control-green.py"
    cases = [  # (label, layout of the five, exit wanted, line index and the text it must hold)
        ("all five green", [g] * 5, 0, None),
        ("check 3 renamed away (the twin)", [g, g, None, g, g], 2, (2, "not found")),
        ("check 2 crashes: plant-crash.py", [g, "plant-crash.py", g, g, g], 2, (1, "crashed")),
        ("check 4 prints nothing: plant-silent.py", [g, g, g, "plant-silent.py", g], 2,
         (3, "printed nothing")),
        ("check 1 prints green, exits 1: plant-disagree.py", ["plant-disagree.py", g, g, g, g], 2,
         (0, "disagree")),
        ("check 5 prints two lines: plant-two-lines.py", [g, g, g, g, "plant-two-lines.py"], 2,
         (4, "2 lines")),
        ("an honest can't tell passes through: cant-tell-honest.py",
         [g, "cant-tell-honest.py", g, g, g], 2, (1, "the fixture could not look")),
        ("check 4 exits 0 with standard error: plant-stderr-on-green.py",
         [g, g, g, "plant-stderr-on-green.py", g], 2, (3, "exited 0 with standard error")),
        ("check 5 opens GREENISH: plant-greenish.py", [g, g, g, g, "plant-greenish.py"], 2,
         (4, "no state")),
        ("check 1 prints an honest red after a handled traceback: plant-red-after-traceback.py",
         ["plant-red-after-traceback.py", g, g, g, g], 1, (0, "RED: fixture: a planted fault")),
        ("check 2 prints a bare green opening: plant-bare-green.py", [g, "plant-bare-green.py", g, g, g],
         2, (1, "no state")),
        ("red outranks can't tell: plant-red.py beside a missing check",
         ["plant-red.py", g, None, g, g], 1, (0, "RED: fixture")),
    ]
    ok_all = True
    try:
        for i, (label, layout, want, probe) in enumerate(cases):
            lines, code = run(tree(f"case{i}", layout))
            ok = code == want and len(lines) == 5
            if probe:
                ok = ok and probe[1] in lines[probe[0]]
            ok_all &= ok
            shown = lines[probe[0]] if probe else lines[0]
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
        print(f"CAN'T TELL: unknown arguments {' '.join(args)}; see --help")
        return 2
    lines, code = run(root)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
