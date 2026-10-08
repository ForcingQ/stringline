#!/usr/bin/env python3
"""Check 3 · derived readers: site/, README.md and CLAUDE.md equal what render.py writes.

What it compares: `python3 render.py --out <scratch>`, run from the repository root into a fresh,
empty scratch folder (so no stale page from an earlier render can be in it), against the WORKING
site/, README.md and CLAUDE.md, read into memory before the render runs: byte for byte, and the
two file lists both ways. Files git ignores under site/ (a Finder .DS_Store) are skipped and
counted in the line. After the render it re-reads the three: anything changed, added or removed
during the run is RED, "the renderer wrote into the tree", whatever the comparison said.
How it is fired: by `checks/run_all.py` (the workflow, on every push and pull request) and by hand
as `python3 checks/derived_readers.py`; its self-test as `--selftest --no-log` by the test runner.
The failure that earned it: hand-kept readers drift from their source; and a reviewer's in-place
stand-in for this check re-rendered over a hand edit, erased it, and read green.
Its twin: a render that writes nothing, a zero-byte file, a room or card page whose body holds no
text, or a README/CLAUDE.md section with no body, is red, never green. The front page is exempt
from the body rule only: the spec gives it no body (its limit line is in its footer).
What it does not prove: that the prose is right, or that the site looks finished; that the
renderer touched nothing outside site/, README.md and CLAUDE.md.
Prints one line: GREEN · ..., RED: <file>: <what>, or CAN'T TELL: <what>, the renderer's own
reason included; exits 0, 1 or 2. A crash of this check is CAN'T TELL.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, 'tests', 'derived_readers')
READERS = ('README.md', 'CLAUDE.md')
FRONT = 'site/index.html'
SKIP = '__pycache__'  # Python's ignored cache folder: the one thing a check may leave behind
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')


class CantTell(Exception):
    pass


def listing(base):
    """Relative paths of the derived files under base: README.md, CLAUDE.md and site/**."""
    found = [r for r in READERS if os.path.isfile(os.path.join(base, r))]
    for d, dirs, files in os.walk(os.path.join(base, 'site')):
        dirs[:] = sorted(x for x in dirs if x != SKIP)
        for f in sorted(files):
            found.append(os.path.relpath(os.path.join(d, f), base).replace(os.sep, '/'))
    return found


def ignored(root):
    """Paths under the three that git ignores; git failing is can't tell, never 'none'."""
    try:
        run = subprocess.run(['git', 'ls-files', '-z', '--others', '--ignored', '--exclude-standard',
                              '--', 'site', *READERS], cwd=root, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise CantTell(f'git could not be run to say which files are ignored ({type(e).__name__})')
    if run.returncode != 0:
        reason = last_line(run.stderr) or f'exit {run.returncode}'
        raise CantTell(f'git could not say which files are ignored ({reason})')
    return {p for p in run.stdout.decode('utf-8', 'replace').split('\0') if p}


def snapshot(base, skip):
    out = {}
    for r in listing(base):
        if r not in skip:
            with open(os.path.join(base, r), 'rb') as f:
                out[r] = f.read()
    return out


def last_line(data):
    lines = [l.strip() for l in data.decode('utf-8', 'replace').splitlines() if l.strip()]
    return lines[-1] if lines else ''


def first_difference(a, b):
    la, lb = a.split(b'\n'), b.split(b'\n')
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i + 1
    return min(len(la), len(lb)) + 1


def empty_body(rel, data):
    """A page whose <main> holds no text past its title, or a reader section with no body."""
    text = data.decode('utf-8', 'replace')
    if rel in READERS:
        lines = text.split('\n')
        heads = [i for i, l in enumerate(lines) if re.match(r'#{1,6} ', l)]
        for n, i in enumerate(heads):
            rest = [l for l in lines[i + 1:] if l.strip()]
            if not rest or re.match(r'#{1,6} ', rest[0]):
                return f'section {n + 1} has no body'
        return None
    if rel == FRONT or not rel.endswith('.html'):
        return None
    m = re.search(r'<main>(.*)</main>', text, re.S)
    body = re.sub(r'<h1>.*?</h1>', '', m.group(1), count=1, flags=re.S) if m else ''
    if not html.unescape(re.sub(r'<[^>]+>', '', body)).strip():
        return 'the render wrote an empty page'
    return None


def check(root):
    """Returns (exit code, line)."""
    if not os.path.isfile(os.path.join(root, 'render.py')):
        return 2, "CAN'T TELL: render.py not found at the repository root"
    try:
        skip = ignored(root)
    except CantTell as e:
        return 2, f"CAN'T TELL: {e}"
    before = snapshot(root, skip)
    with tempfile.TemporaryDirectory() as scratch:
        try:
            run = subprocess.run([sys.executable, 'render.py', '--out', scratch], cwd=root,
                                 env=ENV, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            run = None
            failed = f"CAN'T TELL: render.py could not be run ({type(e).__name__})"
        after = snapshot(root, skip)
        touched = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        if touched:
            more = f' (and {len(touched) - 1} more)' if len(touched) > 1 else ''
            return 1, f'RED: {touched[0]}: the renderer wrote into the tree{more}'
        if run is None:
            return 2, failed
        if run.returncode != 0:
            reason = last_line(run.stderr) or 'no reason given'
            return 2, f"CAN'T TELL: render.py exited {run.returncode}: {reason}"
        if run.stderr.strip():
            return 2, f"CAN'T TELL: render.py exited 0 but wrote to standard error: {last_line(run.stderr)}"
        rendered = snapshot(scratch, set())
    if not rendered:
        return 1, 'RED: render.py: the render wrote nothing'
    reds = [f'{r}: the render did not write it' for r in READERS + (FRONT,) if r not in rendered]
    for r, data in rendered.items():
        if not data:
            reds.append(f'{r}: the render wrote an empty page')
        elif empty_body(r, data):
            reds.append(f'{r}: {empty_body(r, data)}')
    reds += [f'{r}: missing from the tree' for r in rendered if r not in before]
    reds += [f'{r}: not written by the renderer' for r in before if r not in rendered]
    reds += [f'{r}: line {first_difference(data, before[r])} differs from the render'
             for r, data in rendered.items() if r in before and data != before[r]]
    if reds:
        more = f' (and {len(reds) - 1} more)' if len(reds) > 1 else ''
        return 1, f'RED: {reds[0]}{more}'
    return 0, (f'GREEN · read {len(before)} files (site/, README.md, CLAUDE.md; {len(skip)} ignored by '
               'git, skipped) · against a fresh render into an empty scratch folder')


def selftest_cases(case):
    """A scratch tree built from render.py and manual/, a git repository, rendered in place."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, 'tree')
        os.makedirs(tree)
        for name in ('render.py', '.gitignore'):
            shutil.copy(os.path.join(ROOT, name), tree)
        shutil.copytree(os.path.join(ROOT, 'manual'), os.path.join(tree, 'manual'),
                        ignore=shutil.ignore_patterns('tests'))
        if os.path.isfile(os.path.join(ROOT, 'tools', 'runlog.py')):
            os.makedirs(os.path.join(tree, 'tools'))
            shutil.copy(os.path.join(ROOT, 'tools', 'runlog.py'), os.path.join(tree, 'tools'))
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, capture_output=True)
        p = lambda *parts: os.path.join(tree, *parts)
        fixture = lambda name: os.path.join(FIXTURES, name)

        def render_in_place():
            subprocess.run([sys.executable, 'render.py'], cwd=tree, env=ENV, check=True,
                           capture_output=True)

        def swap(path, src):  # replaces a corpus record with a fixture; returns the original bytes
            with open(path, 'rb') as f:
                kept = f.read()
            shutil.copy(src, path)
            return kept

        def put(path, data):
            with open(path, 'wb') as f:
                f.write(data)

        render_in_place()
        before = snapshot(tree, set())
        case('clean control', 0, 'GREEN', check(tree))
        case('the check left the tree as it found it', 0, '', (0 if snapshot(tree, set()) == before else 1, ''))

        put(p('site', '.DS_Store'), b'fixture\n')
        case('a file git ignores under site/ is skipped and counted', 0, '1 ignored by git', check(tree))
        os.remove(p('site', '.DS_Store'))

        with open(fixture('hand-edit-readme.txt'), 'rb') as f:
            edit = f.read()
        put(p('README.md'), before['README.md'] + edit)
        case('hand-edited README', 1, 'RED: README.md: line', check(tree))
        case('the hand edit is still there after the check', 0, '',
             (0 if snapshot(tree, set())['README.md'].endswith(edit) else 1, ''))

        put(p('site', 'stray.html'), b'<p>stray</p>\n')
        put(p('README.md'), before['README.md'])
        case('a page in site/ the renderer does not write', 1, 'RED: site/stray.html: not written', check(tree))
        os.remove(p('site', 'stray.html'))

        shutil.move(p('render.py'), p('render.py.kept'))
        shutil.copy(fixture('writes-in-place-render.py'), p('render.py'))
        put(p('README.md'), before['README.md'] + edit)
        case('a renderer that also writes in place, over a hand edit', 1,
             'RED: README.md: the renderer wrote into the tree', check(tree))
        put(p('README.md'), before['README.md'])
        for name, want, line in (('empty-render.py', 1, 'RED: render.py: the render wrote nothing'),
                                 ('empty-page-render.py', 1, 'the render wrote an empty page'),
                                 ('crash-render.py', 2, 'exited 1: RuntimeError: fixture crash')):
            shutil.copy(fixture(name), p('render.py'))
            case(f'{name[:-3]} stand-in', want, line, check(tree))
        os.remove(p('render.py'))
        case('no render.py', 2, "CAN'T TELL: render.py not found", check(tree))
        shutil.move(p('render.py.kept'), p('render.py'))

        kept = swap(p('manual', 'site.toml'), fixture('empty-owner-site.toml'))
        case('an empty owner', 2, 'owner is empty', check(tree))
        put(p('manual', 'site.toml'), kept)

        for record, src, line in ((('rooms', 'build.toml'), 'empty-body-room.toml',
                                   'RED: site/build.html: the render wrote an empty page'),
                                  (('readers', 'claude.toml'), 'empty-section-reader.toml',
                                   'RED: CLAUDE.md: section 2 has no body')):
            kept = swap(p('manual', *record), fixture(src))
            render_in_place()
            case(f'{src[:-5]} (twin)', 1, line, check(tree))
            put(p('manual', *record), kept)
            render_in_place()

        case('clean control again, after the plants are undone', 0, 'GREEN', check(tree))
        shutil.rmtree(p('.git'))
        case('not a git repository', 2, "CAN'T TELL: git could not say", check(tree))


def selftest():
    results = []

    def case(name, want, text, got):
        ok = got[0] == want and text in got[1]
        results.append(ok)
        print(f'{"PASS" if ok else "FAIL"} · {name} · exit {got[0]}' + (f' · {got[1]}' if got[1] else ''))

    try:
        selftest_cases(case)
    except Exception as e:  # a corpus that cannot render, or a fixture that cannot be read
        print(f"CAN'T TELL · the self-test could not run its cases ({type(e).__name__})")
        print('selftest: FAIL')
        return 2
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
