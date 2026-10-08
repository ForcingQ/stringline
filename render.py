#!/usr/bin/env python3
"""render.py: writes the manual site, README.md and CLAUDE.md from the one source in manual/.

How it is fired: by hand from the repository root (`python3 render.py`, in place, or
`python3 render.py --out <dir>`); by check 3 (`checks/derived_readers.py`), which renders into a
scratch folder and compares; by the test runner as `python3 render.py --selftest --no-log`.
The failure that earned it: a README and an agent's instructions kept by hand beside a manual
fall behind it, quietly. Here the three are written from one set of records, and check 3 is red
the moment any of them differs from what this writes.

It never invents text: everything it writes is a record's field, a list derived from the
records, or a card's "what it has caught" line from tools/runlog.py (imported, never copied).
Standard library only, Python 3.11 or later. Exit 0 on success, 2 when it cannot render.
"""
import html
import os
import re
import shutil
import sys
import tempfile
import tomllib

ROOT = os.path.dirname(os.path.abspath(__file__))

# The keys each kind of record must carry to be rendered. A key outside a record's list is
# check 2's to name (checks/resolution.py); the renderer refuses only what it cannot render.
REQUIRED = {
    'site': ('title', 'owner', 'limit', 'rooms'),
    'room': ('id', 'title', 'body'),
    'term': ('id', 'term', 'body'),
    'reader': ('id', 'sections'),
    'card': ('id', 'name', 'status', 'what', 'first', 'gotcha', 'earned_by'),
}
READERS = (('readme', 'README.md'), ('claude', 'CLAUDE.md'))
OWNER_TOKEN = '{owner}'  # in a reader body, replaced by site.toml's owner
TERMS_ROOM, TOOLS_ROOM, BUILD_ROOM = 'how-it-runs', 'tools', 'build'  # set by SPEC-corpus/SPEC-card
# Card labels: the intent's own words for the card's fields.
CARD_FIELDS = (('what', 'What it is'), ('first', 'The first thing to do'),
               ('gotcha', 'The one gotcha'), ('earned_by', 'The failure that earned it'))
CAUGHT_LABEL = 'What it has caught'
IN_PROGRESS = 'in progress'


class RenderError(Exception):
    """The corpus cannot be rendered as it stands; the message names the file."""


def load(path, kind):
    try:
        with open(path, 'rb') as f:
            rec = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise RenderError(f'{path}: cannot read: {e}')
    missing = [k for k in REQUIRED[kind] if k not in rec]
    if missing:
        raise RenderError(f'{path}: missing {", ".join(missing)}')
    return rec


def load_dir(manual, sub, kind):
    folder = os.path.join(manual, sub)
    if not os.path.isdir(folder):
        return []
    return [load(os.path.join(folder, n), kind)
            for n in sorted(os.listdir(folder)) if n.endswith('.toml')]


def load_corpus(manual):
    if not os.path.isfile(os.path.join(manual, 'site.toml')):
        raise RenderError(f'{manual}: no site.toml')
    site = load(os.path.join(manual, 'site.toml'), 'site')
    rooms = {r['id']: r for r in load_dir(manual, 'rooms', 'room')}
    for rid in site['rooms']:
        if rid not in rooms:
            raise RenderError(f'site.toml: room {rid} has no record')
    readers = {r['id']: r for r in load_dir(manual, 'readers', 'reader')}
    for rid, _ in READERS:
        if rid not in readers:
            raise RenderError(f'readers/{rid}.toml: missing')
    return {'site': site, 'rooms': rooms, 'readers': readers,
            'terms': load_dir(manual, 'terms', 'term'),
            'cards': load_dir(manual, 'tools', 'card')}


# ---- the markdown subset: paragraphs, [text](path), [text](#term:id), *emphasis*, `code`,
# bulleted lists. Every body is escaped first; anything else comes through as written.

LINK = re.compile(r'\[([^\]\n]+)\]\(([^)\s]+)\)')
EMPH = re.compile(r'(?<![*\w])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?![*\w])')


def href(target, depth):
    if target.startswith('#term:'):
        return '../' * depth + f'{TERMS_ROOM}.html#term-{target[len("#term:"):]}'
    return '../' * (depth + 1) + target  # paths are relative to the repository root


def inline(text, depth):
    """Inline markup on already-escaped text; code spans are left untouched."""
    out = []
    for i, part in enumerate(re.split(r'(`[^`\n]+`)', text)):
        if i % 2:
            out.append(f'<code>{part[1:-1]}</code>')
            continue
        part = LINK.sub(lambda m: f'<a href="{href(m.group(2), depth)}">'
                        f'{m.group(1)}</a>', part)
        out.append(EMPH.sub(r'<em>\1</em>', part))
    return ''.join(out)


def markdown(body, depth=0):
    text = html.escape(body.strip('\n'), quote=True)
    blocks = [b for b in re.split(r'\n\s*\n', text) if b.strip()]
    out = []
    for b in blocks:
        lines = b.split('\n')
        if all(l.startswith('- ') for l in lines):
            items = ''.join(f'<li>{inline(l[2:], depth)}</li>' for l in lines)
            out.append(f'<ul>{items}</ul>')
        else:
            out.append(f'<p>{inline(b, depth)}</p>')
    return '\n'.join(out)


# ---- pages


def page(site, title, body_html, depth):
    up = '../' * depth
    rooms = ''.join(f'<li><a href="{up}{rid}.html">{html.escape(t)}</a></li>'
                    for rid, t in site['room_titles'])
    head_title = html.escape(title)
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{head_title}</title>\n</head>\n<body>\n'
            f'<header><p><a href="{up}index.html">{html.escape(site["title"])}</a></p>\n'
            f'<nav><ul>{rooms}</ul></nav></header>\n'
            f'<main>\n<h1>{head_title}</h1>\n{body_html}\n</main>\n'
            f'<footer><p>{html.escape(site["limit"])}</p></footer>\n</body>\n</html>\n')


def runlog_caught_line():
    """The card's fourth field comes from tools/runlog.py; it is imported here, never copied."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    try:
        import runlog
    except ImportError as e:
        raise RenderError(f'tools/runlog.py: cannot import ({e}); a released card needs it')
    finally:
        sys.path.pop(0)
    return runlog.caught_line


def card_page(site, card, caught):
    parts = []
    for key, label in CARD_FIELDS:
        value = (f'<pre><code>{html.escape(card[key])}</code></pre>' if key == 'first'
                 else markdown(card[key], depth=1))
        parts.append(f'<h2>{label}</h2>\n{value}')
    line = caught(card['id'], card.get('catching'))
    parts.append(f'<h2>{CAUGHT_LABEL}</h2>\n<p>{html.escape(line)}</p>')
    return page(site, card['name'], '\n'.join(parts), depth=1)


def render_files(corpus, caught=None):
    """Returns {relative path: text} for everything the renderer writes."""
    site = dict(corpus['site'])
    rooms, cards = corpus['rooms'], corpus['cards']
    site['room_titles'] = [(rid, rooms[rid]['title']) for rid in site['rooms']]
    released = [c for c in cards if c['status'] == 'released']
    building = [c for c in cards if c['status'] == 'building']
    for c in cards:
        if c['status'] not in ('released', 'building'):
            raise RenderError(f'tools/{c["id"]}.toml: status {c["status"]!r}')
    if released and caught is None:
        caught = runlog_caught_line()
    files = {'site/index.html': page(site, site['title'], '', depth=0)}
    for rid in site['rooms']:
        room = rooms[rid]
        body = markdown(room['body'])
        if rid == TOOLS_ROOM and released:
            body += '\n<ul>' + ''.join(f'<li><a href="tools/{c["id"]}.html">{html.escape(c["name"])}'
                                       f'</a>: {html.escape(c["what"])}</li>' for c in released) + '</ul>'
        if rid == BUILD_ROOM and building:
            body += '\n<ul>' + ''.join(f'<li>{html.escape(c["name"])}: {IN_PROGRESS}</li>'
                                       for c in building) + '</ul>'
        if rid == TERMS_ROOM and corpus['terms']:
            body += '\n<dl>' + ''.join(f'<dt id="term-{t["id"]}">{html.escape(t["term"])}</dt>'
                                       f'<dd>{markdown(t["body"])}</dd>' for t in corpus['terms']) + '</dl>'
        files[f'site/{rid}.html'] = page(site, room['title'], body, depth=0)
    for c in released:
        files[f'site/tools/{c["id"]}.html'] = card_page(site, c, caught)
    for rid, name in READERS:
        files[name] = reader_text(corpus['readers'][rid], site['owner'], rid)
    return files


def reader_text(reader, owner, rid):
    """Markdown for README.md / CLAUDE.md: first section a `#` title, the rest `##` headings."""
    sections = reader['sections']
    if not sections:
        raise RenderError(f'readers/{rid}.toml: no sections')
    if rid == 'readme' and not any(OWNER_TOKEN in s.get('body', '') for s in sections):
        raise RenderError(f'readers/{rid}.toml: no {OWNER_TOKEN} signature line')
    out = []
    for i, s in enumerate(sections):
        if 'heading' not in s or 'body' not in s:
            raise RenderError(f'readers/{rid}.toml: section {i + 1} lacks heading or body')
        mark = '#' if i == 0 else '##'
        body = s['body'].strip('\n').replace(OWNER_TOKEN, owner)
        out.append(f'{mark} {s["heading"]}\n\n{body}\n')
    return '\n'.join(out)


def write(files, out):
    """Writes the files under `out`; site/ is wholly derived, so it is replaced, not merged."""
    if os.path.isdir(os.path.join(out, 'site')):
        shutil.rmtree(os.path.join(out, 'site'))
    for rel, text in files.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)


def render(manual, out, caught=None):
    files = render_files(load_corpus(manual), caught)
    write(files, out)
    return files


# ---- self-test: fixture text only; ends with `selftest: PASS` or `selftest: FAIL`.


def selftest():
    results = []

    def case(name, ok):
        results.append(ok)
        print(f'{"PASS" if ok else "FAIL"} · {name}')

    fixture = load(os.path.join(ROOT, 'manual', 'tests', 'markdown-fixture.toml'), 'room')
    got = markdown(fixture['body'])
    case('markdown: paragraph', got.count('<p>') == 2)
    case('markdown: path link', '<a href="../INTENT.md">path link</a>' in got)
    case('markdown: term link', f'<a href="{TERMS_ROOM}.html#term-lane">term link</a>' in got)
    case('markdown: emphasis', '<em>emphasis</em>' in got)
    case('markdown: inline code, nothing applied inside',
         '<code>inline &lt;code&gt; &amp; *not emphasis*</code>' in got)
    case('markdown: bulleted list', got.count('<li>') == 2 and '<li>a list item with <code>code</code></li>' in got)
    case('markdown: outside the subset comes through escaped',
         '&lt;b&gt;raw &amp; &quot;html&quot;&lt;/b&gt; &#x27;quoted&#x27;' in got and '<b>' not in got
         and '**strong**' in got and '# a heading' in got and '1. a number' in got)

    with tempfile.TemporaryDirectory() as tmp:
        manual = os.path.join(tmp, 'manual')
        shutil.copytree(os.path.join(ROOT, 'manual'), manual,
                        ignore=shutil.ignore_patterns('tests', 'tools'))
        os.makedirs(os.path.join(manual, 'tools'))
        card = ('name = "Sample released"\nstatus = "released"\nwhat = "A *fixture* tool."\n'
                'first = "python3 tools/sample/sample.py <file>"\ngotcha = "It reads `stdin` only."\n'
                'earned_by = "A fixture failure."\nfiles = ["tools/sample/sample.py"]\n'
                'catching = ["exact", "absent"]\nverified_against = ""\n')
        with open(os.path.join(manual, 'tools', 'sample.toml'), 'w') as f:
            f.write('id = "sample"\n' + card)
        with open(os.path.join(manual, 'tools', 'sample-building.toml'), 'w') as f:
            f.write('id = "sample-building"\nname = "Sample building"\nstatus = "building"\n'
                    'what = "w"\nfirst = "f"\ngotcha = "g"\nearned_by = "e"\nfiles = []\n'
                    'verified_against = ""\n')
        calls = []

        def stub(tool, catching=None):
            calls.append((tool, catching))
            return 'no real run yet'

        a, b = os.path.join(tmp, 'a'), os.path.join(tmp, 'b')
        fa = render(manual, a, stub)
        render(manual, a, stub)  # twice into the same place
        fb = render(manual, b, stub)
        same = fa == fb and all(open(os.path.join(a, p), encoding='utf-8').read() == t
                                for p, t in fb.items())
        case('render twice: byte-identical', same)
        case('render: no empty file', all(fa.values()))
        case('front page carries the limit line',
             'That it mirrors that work is the owner' in fa['site/index.html'])
        case('README signature reads the owner from site.toml', 'Chad Wallace' in fa['README.md']
             and OWNER_TOKEN not in fa['README.md'])
        page_ = fa.get('site/tools/sample.html', '')
        case('released card renders every field', all(l in page_ for _, l in CARD_FIELDS)
             and '<em>fixture</em>' in page_ and '&lt;file&gt;' in page_ and CAUGHT_LABEL in page_)
        case('caught line comes from runlog.caught_line with the card\'s catching',
             calls and set(map(repr, calls)) == {repr(('sample', ['exact', 'absent']))} and 'no real run yet' in page_)
        case('building card: absent from tools room, in progress in build room',
             'Sample building' not in fa['site/tools.html']
             and f'Sample building: {IN_PROGRESS}' in fa['site/build.html']
             and 'site/tools/sample-building.html' not in fa)
        with open(os.path.join(manual, 'readers', 'readme.toml'), encoding='utf-8') as f:
            text = f.read()
        with open(os.path.join(manual, 'readers', 'readme.toml'), 'w', encoding='utf-8') as f:
            f.write(text.replace(OWNER_TOKEN, 'someone'))
        try:
            render(manual, os.path.join(tmp, 'c'), stub)
            case('README without the owner signature is refused', False)
        except RenderError:
            case('README without the owner signature is refused', True)
        os.remove(os.path.join(manual, 'site.toml'))
        try:
            render(manual, os.path.join(tmp, 'd'), stub)
            case('a corpus with no site.toml is refused', False)
        except RenderError:
            case('a corpus with no site.toml is refused', True)

    ok = all(results)
    print(f'selftest: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


def main(argv):
    args = [a for a in argv if a != '--no-log']  # accepted and ignored: the renderer writes no log
    if args == ['--selftest']:
        return selftest()
    out = ROOT
    if len(args) == 2 and args[0] == '--out':
        out = os.path.abspath(args[1])
    elif args:
        print('usage: render.py [--out DIR] [--selftest] [--no-log]', file=sys.stderr)
        return 2
    try:
        files = render(os.path.join(ROOT, 'manual'), out)
    except RenderError as e:
        print(f'CAN\'T RENDER: {e}', file=sys.stderr)
        return 2
    print(f'wrote {len(files)} files under {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
