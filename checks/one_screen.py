#!/usr/bin/env python3
"""Check 4 · one screen: every page of prose and every record fits on one screen.

What it compares: every *.md in the repository's top folder and every record under manual/, at
every depth (manual/**/*.toml), against 60 source lines. A line is a newline-terminated line,
plus one for an unterminated last line, so the count reads the same on every machine.
How it is fired: by checks/run_all.py on every push and pull request (the workflow), and by hand,
`python3 checks/one_screen.py` from anywhere in the repository. It reports; it never stops work.
The failure that earned it: the one-screen rule was a convention kept by eye in the owner's
earlier manuals, and a page that grew past a screen was noticed only when a reader complained.
Its twin: zero files found is RED, never green: a check that finds nothing to read is blind.
What it does not prove: how many screen rows a page takes when its long lines wrap; that a page
is clear. It does not read code files, run rows (runs/) or anything below the top folder except
manual/, and its line says so. It reads the working files, tracked or not, dot-named ones included.
A bare carriage return is not a line ending, by the definition above (a named limit).

Output, one line: `GREEN · read <n> files ...`, `RED: <file>: <count> source lines ...` or
`CAN'T TELL: <what it could not read>`; exit 0, 1 or 2.
  one_screen.py [--root DIR]     DIR defaults to the folder above checks/
  one_screen.py --selftest       its committed fixtures in checks/tests/one_screen/
"""
import os
import shutil
import sys
import tempfile

LIMIT = 60
HERE = os.path.dirname(os.path.abspath(__file__))
NOT_READ = "code files and run rows not read"


def count_lines(path):
    with open(path, "rb") as f:
        data = f.read()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def run(root):
    # listdir and walk, not glob: glob skips names that open with a dot
    files = sorted(os.path.join(root, n) for n in os.listdir(root)
                   if n.endswith(".md") and not os.path.isdir(os.path.join(root, n)))
    for dirpath, dirnames, names in os.walk(os.path.join(root, "manual")):
        dirnames.sort()
        files += sorted(os.path.join(dirpath, n) for n in names if n.endswith(".toml"))
    if not files:
        return f"RED: found zero files (top-folder *.md, manual/**/*.toml): blind · {NOT_READ}", 1
    over, cant = [], []
    for p in files:
        rel = os.path.relpath(p, root)
        try:
            n = count_lines(p)
        except OSError as e:
            cant.append(f"{rel} ({e.strerror or e.__class__.__name__})")
            continue
        if n > LIMIT:
            over.append((rel, n))
    if over:
        rel, n = over[0]
        more = f"; {len(over)} files over in all" if len(over) > 1 else ""
        also = f"; could not read {len(cant)}: {cant[0]}" if cant else ""
        return f"RED: {rel}: {n} source lines, over {LIMIT}{more}{also}", 1
    if cant:
        return f"CAN'T TELL: could not read {len(cant)} of {len(files)} files, first {cant[0]}", 2
    return (f"GREEN · read {len(files)} files (top-folder *.md, manual/**/*.toml) · against"
            f" {LIMIT} source lines each · {NOT_READ}"), 0


def selftest():
    fix = os.path.join(HERE, "tests", "one_screen")
    cases = [("plant-61-lines", 1), ("plant-unterminated", 1), ("plant-manual-deep", 1),
             ("plant-dot-page", 1), ("control-60-lines", 0), ("control-bare-cr", 0),
             ("twin-no-files", 1)]
    ok_all = True
    for name, want in cases:
        line, code = run(os.path.join(fix, name))
        ok = code == want
        ok_all &= ok
        print(f"{'ok  ' if ok else 'FAIL'} · {name} · want {want}, got {code} · {line}")
    scratch = tempfile.mkdtemp(prefix="one-screen-selftest-")
    try:
        root = os.path.join(scratch, "unreadable")
        shutil.copytree(os.path.join(fix, "control-60-lines"), root)
        os.symlink("no-such-page.md", os.path.join(root, "BROKEN.md"))
        line, code = run(root)
        ok = code == 2
        ok_all &= ok
        print(f"{'ok  ' if ok else 'FAIL'} · unreadable (control-60-lines plus a page that cannot be"
              f" opened) · want 2, got {code} · {line}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
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
    except Exception as e:  # a crash is never green
        line, code = f"CAN'T TELL: the check failed: {e.__class__.__name__}: {e}", 2
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
