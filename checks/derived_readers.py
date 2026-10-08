#!/usr/bin/env python3
"""Check 3 · derived readers: site/, README.md and CLAUDE.md equal what render.py writes.

What it compares: `python3 render.py --out <scratch>`, run from the repository root, against the
WORKING site/, README.md and CLAUDE.md, byte for byte, and the two file lists both ways. It writes
only into its scratch folder and touches nothing in the tree.
How it is fired: by `checks/run_all.py` (the workflow, on every push and pull request) and by hand
as `python3 checks/derived_readers.py`; its self-test as `--selftest --no-log` by the test runner.
The failure that earned it: hand-kept readers drift from their source; and a reviewer's in-place
stand-in for this check re-rendered over a hand edit, erased it, and read green.
Its twin: a render that writes nothing, or writes an empty page, is red, never green.
What it does not prove: that the prose is right, or that the site looks finished.
Prints one line: GREEN · ..., RED: <file>: <what>, or CAN'T TELL: <what>; exits 0, 1 or 2.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, 'tests', 'derived_readers')
READERS = ('README.md', 'CLAUDE.md')
SKIP = '__pycache__'  # Python's ignored cache folder: the one thing a check may leave behind


def listing(base):
    """Relative paths of the derived files under base: README.md, CLAUDE.md and site/**."""
    found = [r for r in READERS if os.path.isfile(os.path.join(base, r))]
    site = os.path.join(base, 'site')
    for d, dirs, files in os.walk(site):
        dirs[:] = sorted(x for x in dirs if x != SKIP)
        for f in sorted(files):
            found.append(os.path.relpath(os.path.join(d, f), base).replace(os.sep, '/'))
    return found


def first_difference(a, b):
    la, lb = a.split(b'\n'), b.split(b'\n')
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i + 1
    return min(len(la), len(lb)) + 1


def check(root):
    """Returns (exit code, line)."""
    if not os.path.isfile(os.path.join(root, 'render.py')):
        return 2, "CAN'T TELL: render.py not found at the repository root"
    with tempfile.TemporaryDirectory() as scratch:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        try:
            run = subprocess.run([sys.executable, 'render.py', '--out', scratch], cwd=root,
                                 env=env, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            return 2, f"CAN'T TELL: render.py could not be run ({type(e).__name__})"
        if run.returncode != 0:
            return 2, f"CAN'T TELL: render.py exited {run.returncode}"
        if run.stderr.strip():
            return 2, "CAN'T TELL: render.py exited 0 but wrote to standard error"
        rendered = listing(scratch)
        if not rendered:
            return 1, 'RED: render.py: the render wrote nothing'
        reds = [f'{r}: the render did not write it' for r in READERS + ('site/index.html',)
                if r not in rendered]
        reds += [f'{r}: the render wrote an empty page' for r in rendered
                 if os.path.getsize(os.path.join(scratch, r)) == 0]
        working = listing(root)
        reds += [f'{r}: missing from the tree' for r in rendered if r not in working]
        reds += [f'{r}: not written by the renderer' for r in working if r not in rendered]
        for r in rendered:
            if r in working:
                with open(os.path.join(scratch, r), 'rb') as f:
                    new = f.read()
                with open(os.path.join(root, r), 'rb') as f:
                    old = f.read()
                if new != old:
                    reds.append(f'{r}: line {first_difference(new, old)} differs from the render')
    if reds:
        more = f' (and {len(reds) - 1} more)' if len(reds) > 1 else ''
        return 1, f'RED: {reds[0]}{more}'
    return 0, (f'GREEN · read {len(working)} files (site/, README.md, CLAUDE.md) · '
               'against a fresh render into a scratch folder')


def snapshot(base):
    out = {}
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != SKIP]
        for f in files:
            with open(os.path.join(d, f), 'rb') as fh:
                out[os.path.relpath(os.path.join(d, f), base)] = fh.read()
    return out


def selftest():
    """Builds a scratch tree from render.py and manual/, renders it in place, then plants."""
    results = []

    def case(name, want, got):
        ok = got[0] == want
        results.append(ok)
        print(f'{"PASS" if ok else "FAIL"} · {name} · exit {got[0]} · {got[1]}')

    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, 'tree')
        os.makedirs(tree)
        shutil.copy(os.path.join(ROOT, 'render.py'), tree)
        shutil.copytree(os.path.join(ROOT, 'manual'), os.path.join(tree, 'manual'))
        if os.path.isfile(os.path.join(ROOT, 'tools', 'runlog.py')):
            os.makedirs(os.path.join(tree, 'tools'))
            shutil.copy(os.path.join(ROOT, 'tools', 'runlog.py'), os.path.join(tree, 'tools'))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable, 'render.py'], cwd=tree, env=env, check=True,
                       capture_output=True)

        before = snapshot(tree)
        case('clean control', 0, check(tree))
        results.append(snapshot(tree) == before)
        print(f'{"PASS" if results[-1] else "FAIL"} · the check left the tree as it found it')

        with open(os.path.join(FIXTURES, 'hand-edit-readme.txt'), encoding='utf-8') as f:
            edit = f.read()
        with open(os.path.join(tree, 'README.md'), 'a', encoding='utf-8') as f:
            f.write(edit)
        case('hand-edited README', 1, check(tree))
        results.append(snapshot(tree)[os.path.join('README.md')].endswith(edit.encode()))
        print(f'{"PASS" if results[-1] else "FAIL"} · the hand edit is still there after the check')
        with open(os.path.join(tree, 'README.md'), 'wb') as f:
            f.write(before['README.md'])

        extra = os.path.join(tree, 'site', 'stray.html')
        with open(extra, 'w') as f:
            f.write('<p>stray</p>\n')
        case('a page in site/ the renderer does not write', 1, check(tree))
        os.remove(extra)

        real = os.path.join(tree, 'render.py')
        shutil.move(real, real + '.kept')
        for fixture, want, name in (('empty-render.py', 1, 'empty render (twin)'),
                                    ('empty-page-render.py', 1, 'empty page (twin)'),
                                    ('crash-render.py', 2, 'renderer crashes')):
            shutil.copy(os.path.join(FIXTURES, fixture), real)
            case(name, want, check(tree))
        os.remove(real)
        case('no render.py', 2, check(tree))
        shutil.move(real + '.kept', real)
        case('clean control again, after the plants are undone', 0, check(tree))

    ok = all(results)
    print(f'selftest: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


def main(argv):
    args = [a for a in argv if a != '--no-log']  # accepted and ignored: checks write no log
    if args == ['--selftest']:
        return selftest()
    if args:
        print('usage: derived_readers.py [--selftest] [--no-log]', file=sys.stderr)
        return 2
    try:
        code, line = check(ROOT)
    except Exception as e:  # a crash is can't tell, never green
        code, line = 2, f"CAN'T TELL: the check crashed ({type(e).__name__})"
    print(line)
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
