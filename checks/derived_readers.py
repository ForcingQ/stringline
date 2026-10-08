#!/usr/bin/env python3
"""Check 3 · derived readers: site/, README.md and CLAUDE.md equal what render.py writes.

What it compares: it copies what the renderer reads (render.py, manual/, and runs/ and
tools/runlog.py when present) into a scratch folder, runs `render.py --out` there into a second,
fresh and empty scratch folder (so no stale page can be in it), and compares that render with the
WORKING site/, README.md and CLAUDE.md, read into memory first: byte for byte, and the two file
lists both ways. The renderer never runs from the tree, so it cannot write into it. As a second
layer, the three are re-read after the run: anything changed, added or removed is RED, "the
renderer wrote into the tree" (a renderer that reaches the tree by a path of its own). Files git
ignores under site/ (a Finder .DS_Store) are skipped and counted in the line.
How it is fired: by `checks/run_all.py` (the workflow, on every push and pull request) and by hand
as `python3 checks/derived_readers.py`; its self-test as `--selftest --no-log` by the test runner.
The failure that earned it: hand-kept readers drift from their source; and a reviewer's in-place
stand-in for this check re-rendered over a hand edit, erased it, and read green.
Its twin: a render that writes nothing, a zero-byte file, or a room or card page whose body holds
no text is red, never green (the front page is exempt from the body rule: the spec gives it no
body). A README or CLAUDE.md section whose record body has no visible text is red; sections are
read from manual/readers/, never by parsing `#` lines out of the rendered file.
What it does not prove: that the prose is right, or that the site looks finished; that a renderer
reaching outside its folders touched nothing but site/, README.md and CLAUDE.md; that a room body
whose markup renders no text (a lone `- `) is not hidden by a derived list that fills its page
(the how-it-runs terms, the tools room's cards). Visible text is as render.py's header says.
Absolute paths in any line it prints are cut to their last component.
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
import tomllib
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, 'tests', 'derived_readers')
READERS = {'readme': 'README.md', 'claude': 'CLAUDE.md'}
FRONT = 'site/index.html'
SKIP = '__pycache__'  # Python's ignored cache folder: the one thing a check may leave behind
SOURCES = ('render.py', 'manual', 'runs', os.path.join('tools', 'runlog.py'))  # what render reads


class CantTell(Exception):
    pass


def env(cwd=None):
    """The environment a command runs in; for the renderer, PWD names the scratch copy, so a
    renderer that writes under its working folder writes into the copy, never the tree."""
    out = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    out.pop('OLDPWD', None)
    if cwd:
        out['PWD'] = cwd
    return out


# Letters and symbols with no visible glyph of their own: the Hangul fillers and the blank
# Braille pattern. Unicode gives them ordinary categories, so they are named here.
BLANK = {'\u115f', '\u1160', '\u3164', '\uffa0', '\u2800'}


def visible(text):
    """True when text holds a character with a visible glyph: not white space or a separator
    (Z*), not a control, format or unassigned code (C*), not a combining mark alone (M*), and not
    one of the blank-looking letters in BLANK."""
    return isinstance(text, str) and any(
        not unicodedata.category(ch).startswith(('Z', 'C', 'M')) and ch not in BLANK for ch in text)


def listing(base):
    """Relative paths of the derived files under base: README.md, CLAUDE.md and site/**."""
    found = [r for r in READERS.values() if os.path.isfile(os.path.join(base, r))]
    for d, dirs, files in os.walk(os.path.join(base, 'site')):
        dirs[:] = sorted(x for x in dirs if x != SKIP)
        for f in sorted(files):
            found.append(os.path.relpath(os.path.join(d, f), base).replace(os.sep, '/'))
    return found


def ignored(root):
    """Paths under the three that git ignores; git failing is can't tell, never 'none'."""
    try:
        run = subprocess.run(['git', 'ls-files', '-z', '--others', '--ignored', '--exclude-standard',
                              '--', 'site', *READERS.values()], cwd=root, capture_output=True, timeout=60)
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


def copy_sources(root, dest):
    """Copies what the renderer reads; the renderer then runs from dest, never from the tree."""
    for rel in SOURCES:
        src = os.path.join(root, rel)
        if os.path.isdir(src):
            # links are copied as links, so the renderer's own gate refuses them here as it
            # would in the tree (copied as files, a link would read green in this check)
            shutil.copytree(src, os.path.join(dest, rel), symlinks=True,
                            ignore=shutil.ignore_patterns(SKIP))
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(dest, rel)) or dest, exist_ok=True)
            shutil.copy(src, os.path.join(dest, rel))


# An absolute path starts a token (after a space, a quote or a bracket), never inside one, so a
# repository-relative path such as manual/site.toml is left whole.
ABSOLUTE = re.compile(r'(?<![\w.~-])(?:[A-Za-z]:|~)?[\\/](?:[^\s\'"\\/:]+[\\/])*([^\s\'"\\/:]+)')


def last_line(data):
    """The last line a command printed, any absolute path in it cut to its last component."""
    lines = [l.strip() for l in data.decode('utf-8', 'replace').splitlines() if l.strip()]
    return ABSOLUTE.sub(r'\1', lines[-1]) if lines else ''


def first_difference(a, b):
    la, lb = a.split(b'\n'), b.split(b'\n')
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i + 1
    return min(len(la), len(lb)) + 1


def empty_sections(manual):
    """Red lines for reader sections whose record body has no visible text."""
    reds = []
    for rid, name in READERS.items():
        path = os.path.join(manual, 'readers', f'{rid}.toml')
        if not os.path.isfile(path):
            continue  # the renderer refuses a missing reader; its reason reaches the line
        try:
            with open(path, 'rb') as f:
                sections = tomllib.load(f).get('sections', [])
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise CantTell(f'manual/readers/{rid}.toml could not be read ({type(e).__name__})')
        reds += [f'{name}: section {n} has no body' for n, s in enumerate(sections, 1)
                 if not visible(s.get('body'))]
    return reds


def empty_page(rel, data):
    """A room or card page whose <main> holds no text past its title."""
    if rel == FRONT or not rel.endswith('.html'):
        return False
    m = re.search(r'<main>(.*)</main>', data.decode('utf-8', 'replace'), re.S)
    body = re.sub(r'<h1>.*?</h1>', '', m.group(1), count=1, flags=re.S) if m else ''
    return not visible(html.unescape(re.sub(r'<[^>]+>', '', body)))


def check(root):
    """Returns (exit code, line)."""
    if not os.path.isfile(os.path.join(root, 'render.py')):
        return 2, "CAN'T TELL: render.py not found at the repository root"
    try:
        skip = ignored(root)
    except CantTell as e:
        return 2, f"CAN'T TELL: {e}"
    before = snapshot(root, skip)
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
        copy_sources(root, src)
        try:
            run = subprocess.run([sys.executable, 'render.py', '--out', out], cwd=src,
                                 env=env(src), capture_output=True, timeout=120)
            failed = None
        except (OSError, subprocess.SubprocessError) as e:
            run, failed = None, f"CAN'T TELL: render.py could not be run ({type(e).__name__})"
        after = snapshot(root, skip)
        touched = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        if touched:
            more = f' (and {len(touched) - 1} more)' if len(touched) > 1 else ''
            return 1, f'RED: {touched[0]}: the renderer wrote into the tree{more}'
        if failed:
            return 2, failed
        if run.returncode != 0:
            reason = last_line(run.stderr) or 'no reason given'
            return 2, f"CAN'T TELL: render.py exited {run.returncode}: {reason}"
        if run.stderr.strip():
            return 2, f"CAN'T TELL: render.py exited 0 but wrote to standard error: {last_line(run.stderr)}"
        rendered = snapshot(out, set())
        try:
            sections = empty_sections(os.path.join(src, 'manual'))
        except CantTell as e:
            return 2, f"CAN'T TELL: {e}"
    if not rendered:
        return 1, 'RED: render.py: the render wrote nothing'
    reds = [f'{r}: the render did not write it' for r in (*READERS.values(), FRONT) if r not in rendered]
    reds += [f'{r}: the render wrote an empty page' for r, data in rendered.items()
             if not data or empty_page(r, data)]
    reds += sections
    reds += [f'{r}: missing from the tree' for r in rendered if r not in before]
    reds += [f'{r}: not written by the renderer' for r in before if r not in rendered]
    reds += [f'{r}: line {first_difference(data, before[r])} differs from the render'
             for r, data in rendered.items() if r in before and data != before[r]]
    if reds:
        more = f' (and {len(reds) - 1} more)' if len(reds) > 1 else ''
        return 1, f'RED: {reds[0]}{more}'
    return 0, (f'GREEN · read {len(before)} files (site/, README.md, CLAUDE.md; {len(skip)} ignored by '
               'git, skipped) · against a render run from a scratch copy into an empty scratch folder')


def selftest_cases(case):
    """A scratch tree built from render.py and manual/, a git repository, rendered in place."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, 'tree')
        os.makedirs(tree)
        shutil.copy(os.path.join(ROOT, '.gitignore'), tree)
        copy_sources(ROOT, tree)
        shutil.rmtree(os.path.join(tree, 'manual', 'tests'), ignore_errors=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, capture_output=True)
        p = lambda *parts: os.path.join(tree, *parts)
        fixture = lambda name: os.path.join(FIXTURES, name)

        def render_in_place():
            subprocess.run([sys.executable, 'render.py'], cwd=tree, env=env(), check=True,
                           capture_output=True)

        def read(path):
            with open(path, 'rb') as f:
                return f.read()

        def put(path, data):
            with open(path, 'wb') as f:
                f.write(data)

        render_in_place()
        before = snapshot(tree, set())
        edit = read(fixture('hand-edit-readme.txt'))
        case('clean control', 0, 'GREEN', check(tree))
        case('the check left the tree as it found it', 0, '', (0 if snapshot(tree, set()) == before else 1, ''))

        put(p('site', '.DS_Store'), b'fixture\n')
        case('a file git ignores under site/ is skipped and counted', 0, '1 ignored by git', check(tree))
        os.remove(p('site', '.DS_Store'))

        put(p('README.md'), before['README.md'] + edit)
        case('hand-edited README', 1, 'RED: README.md: line 36 differs from the render', check(tree))
        case('the hand edit is still there after the check', 0, '',
             (0 if read(p('README.md')).endswith(edit) else 1, ''))

        put(p('site', 'stray.html'), b'<p>stray</p>\n')
        put(p('README.md'), before['README.md'])
        case('a page in site/ the renderer does not write', 1,
             'RED: site/stray.html: not written by the renderer', check(tree))
        os.remove(p('site', 'stray.html'))

        real = read(p('render.py'))
        put(p('README.md'), before['README.md'] + edit)
        put(p('render.py'), read(fixture('writes-in-place-render.py')))
        case('a renderer that also writes in place, over a hand edit', 1,
             'RED: CLAUDE.md: the render did not write it', check(tree))
        case('the in-place renderer could not touch the hand edit', 0, '',
             (0 if read(p('README.md')).endswith(edit) else 1, ''))
        put(p('render.py'), read(fixture('writes-into-tree-render.py')))
        os.environ['FIXTURE_TREE'] = tree
        try:
            case('a renderer that reaches the tree by its own path (second layer)', 1,
                 'RED: README.md: the renderer wrote into the tree', check(tree))
        finally:
            del os.environ['FIXTURE_TREE']
        put(p('README.md'), before['README.md'] + edit)
        put(p('render.py'), read(fixture('writes-under-pwd-render.py')))
        kept_pwd = os.environ.get('PWD')
        os.environ['PWD'] = tree  # as if the shell were in the tree when the check ran
        try:
            case('a renderer that writes under $PWD, with the shell in the tree', 1,
                 'RED: CLAUDE.md: the render did not write it', check(tree))
        finally:
            if kept_pwd is None:
                del os.environ['PWD']
            else:
                os.environ['PWD'] = kept_pwd
        case('the $PWD renderer could not touch the hand edit', 0, '',
             (0 if read(p('README.md')).endswith(edit) else 1, ''))
        put(p('README.md'), before['README.md'])
        for name, want, line in (('empty-render.py', 1, 'RED: render.py: the render wrote nothing'),
                                 ('empty-page-render.py', 1, 'RED: README.md: the render wrote an empty page'),
                                 ('empty-main-render.py', 1, 'RED: site/build.html: the render wrote an empty page'),
                                 ('crash-render.py', 2, "CAN'T TELL: render.py exited 1: RuntimeError: fixture crash"),
                                 ('crash-with-path-render.py', 2,
                                  "CAN'T TELL: render.py exited 1: RuntimeError: fixture crash in render.py")):
            put(p('render.py'), read(fixture(name)))
            case(f'{name[:-3]} stand-in', want, line, check(tree))
        os.remove(p('render.py'))
        case('no render.py', 2, "CAN'T TELL: render.py not found at the repository root", check(tree))
        put(p('render.py'), real)

        for record, src, want, line, rerender in (
                (('site.toml',), 'empty-owner-site.toml', 2, 'owner is empty', False),
                (('rooms', 'build.toml'), 'empty-body-room.toml', 2, 'body has no visible text', False),
                (('readers', 'claude.toml'), 'empty-section-reader.toml', 1,
                 'RED: CLAUDE.md: section 2 has no body', True),
                (('readers', 'claude.toml'), 'invisible-section-reader.toml', 1,
                 'RED: CLAUDE.md: section 2 has no body', True),
                (('readers', 'claude.toml'), 'comment-lines-reader.toml', 0, 'GREEN', True)):
            kept = read(p('manual', *record))
            put(p('manual', *record), read(fixture(src)))
            if rerender:
                render_in_place()
            case(src[:-5], want, line, check(tree))
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
