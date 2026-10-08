#!/usr/bin/env python3
"""render.py: writes the manual site, README.md and CLAUDE.md from the one source in manual/.

How it is fired: by hand from the repository root (`python3 render.py`, in place, or
`python3 render.py --out <dir>`); by check 3 (`checks/derived_readers.py`), which renders into a
fresh scratch folder and compares; by the test runner as `python3 render.py --selftest --no-log`.
The failure that earned it: a README and an agent's instructions kept by hand beside a manual
fall behind it, quietly. Here the three are written from one set of records, and check 3 is red
the moment any of them differs from what this writes.

It never invents text: everything it writes is a record's field, a list derived from the
records, or a card's "what it has caught" line from tools/runlog.py (imported, never copied).
The one exception is structure the spec names but gives no record, kept in this code: four card
labels are INTENT.md's words (what it is, the first thing to do, the one gotcha, what it has
caught), "The failure that earned it" is SPEC.md's phrase, and "in progress" is SPEC-card.md's.
The look is held beside the records in manual/look/: style.css is written into every page's
head as one style block (its {fonts} token replaced by the page's own way to site/fonts/), and
every file in manual/look/fonts/ is copied to site/fonts/ byte for byte. Refused, one line, exit
2: a style block that is missing, empty or holds a closing style tag; a font the block names
that is not there; any file in the fonts folder, whatever its ending, with no
LICENSE-<face>.txt beside it (the face is its name up to the first hyphen or full stop), or no
NOTICE.txt (a face never ships bare); a folder that cannot be read. And one gate over every read: a symbolic link
anywhere under manual/, the folder itself included, is refused, because a followed link could
publish a file from elsewhere on the machine. Not seen by that gate: a hard link, which is a
file like any other. Dot-files and
sub-folders there are skipped. The front page lists the rooms: each room's title and the first
block of its body, whole. The current room is marked in the nav with aria-current.
In place, site/ is wholly derived and is replaced; under `--out <dir>` it writes only the files
it renders and deletes nothing. Standard library only, Python 3.11 or later.
Visible text: at least one character outside Unicode's Z, C and M categories and not a
blank-looking letter (Hangul fillers, blank Braille); an owner, a room body or a card's what
without one is refused. Exit 0 on success, 2 when it cannot render (the reason on standard
error, one line).
"""
import html
import os
import re
import shutil
import sys
import tempfile
import tomllib
import unicodedata

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
# Card labels (structure, not record text): INTENT.md's words, but earned_by's, which is SPEC.md's.
CARD_FIELDS = (('what', 'What it is'), ('first', 'The first thing to do'),
               ('gotcha', 'The one gotcha'), ('earned_by', 'The failure that earned it'))
CAUGHT_LABEL = 'What it has caught'
IN_PROGRESS = 'in progress'
ID = re.compile(r'[a-z0-9-]+')  # an id becomes a file name and an HTML id: nothing else gets in
RESERVED_ROOMS = ('index',)  # a room called index would replace the front page


# Letters and symbols with no visible glyph of their own: the Hangul fillers and the blank
# Braille pattern. Unicode gives them ordinary categories, so they are named here.
BLANK = {'\u115f', '\u1160', '\u3164', '\uffa0', '\u2800'}


def visible(text):
    """True when text holds a character with a visible glyph: not white space or a separator
    (Z*), not a control, format or unassigned code (C*), not a combining mark alone (M*), and not
    one of the blank-looking letters in BLANK."""
    return isinstance(text, str) and any(
        not unicodedata.category(ch).startswith(('Z', 'C', 'M')) and ch not in BLANK for ch in text)


class RenderError(Exception):
    """The corpus cannot be rendered as it stands; the message names the file."""


def load(path, kind, base):
    shown = os.path.relpath(path, base)
    try:
        with open(path, 'rb') as f:
            rec = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise RenderError(f'{shown}: cannot read: {e.strerror if isinstance(e, OSError) else e}')
    missing = [k for k in REQUIRED[kind] if k not in rec]
    if missing:
        raise RenderError(f'{shown}: missing {", ".join(missing)}')
    if kind in ('room', 'term', 'card') and not (isinstance(rec['id'], str) and ID.fullmatch(rec['id'])):
        raise RenderError(f'{shown}: id {rec["id"]!r} is not lower-case letters, digits and hyphens')
    return rec


def load_dir(manual, sub, kind):
    folder = os.path.join(manual, sub)
    if not os.path.isdir(folder):
        return []
    base = os.path.dirname(manual)
    return [load(os.path.join(folder, n), kind, base)
            for n in sorted(os.listdir(folder)) if n.endswith('.toml')]


def no_links(manual):
    """One gate for every read: nothing under manual/ is reached through a link. A link could
    bring a file from anywhere on the machine into pages, readers and font files that are
    published. The folder itself, every folder under it and every file are looked at, and the
    walk never follows a link."""
    if os.path.islink(manual):
        raise RenderError('manual: a link, not a folder')
    for d, dirs, files in os.walk(manual, followlinks=False):
        for name in sorted(dirs + files):
            path = os.path.join(d, name)
            if os.path.islink(path):
                rel = os.path.relpath(path, manual).replace(os.sep, '/')
                raise RenderError(f'manual/{rel}: a link, not a file or folder')


def load_corpus(manual):
    base = os.path.dirname(manual)
    no_links(manual)
    if not os.path.isfile(os.path.join(manual, 'site.toml')):
        raise RenderError(f'{os.path.relpath(manual, base)}: no site.toml')
    site = load(os.path.join(manual, 'site.toml'), 'site', base)
    if not visible(site['owner']):
        raise RenderError('manual/site.toml: owner is empty; the README signature needs a name')
    rooms = {r['id']: r for r in load_dir(manual, 'rooms', 'room')}
    for rid, room in rooms.items():
        if rid in RESERVED_ROOMS:
            raise RenderError(f'manual/rooms/{rid}.toml: the room id {rid} is reserved for the front page')
        if not visible(room['body']):
            raise RenderError(f'manual/rooms/{rid}.toml: body has no visible text')
    for rid in site['rooms']:
        if rid not in rooms:
            raise RenderError(f'manual/site.toml: room {rid} has no record')
    readers = {r['id']: r for r in load_dir(manual, 'readers', 'reader')}
    for rid, _ in READERS:
        if rid not in readers:
            raise RenderError(f'manual/readers/{rid}.toml: missing')
    return {'site': site, 'rooms': rooms, 'readers': readers,
            'terms': load_dir(manual, 'terms', 'term'),
            'cards': load_dir(manual, 'tools', 'card'), 'look': load_look(manual)}


# ---- the markdown subset: paragraphs, [text](path), [text](#term:id), *emphasis*, `code`,
# bulleted lists. Every body is escaped first; anything else comes through as written.
# Emphasis applies to text and link text, never to a link's address or inside code.

LINK = re.compile(r'\[([^\]\n]+)\]\(([^)\s]+)\)')
EMPH = re.compile(r'(?<![*\w])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?![*\w])')


def href(target, depth):
    if target.startswith('#term:'):
        return '../' * depth + f'{TERMS_ROOM}.html#term-{target[len("#term:"):]}'
    return '../' * (depth + 1) + target  # paths are relative to the repository root


def emph(text):
    return EMPH.sub(r'<em>\1</em>', text)


def inline(text, depth):
    """Inline markup on already-escaped text."""
    out = []
    for i, part in enumerate(re.split(r'(`[^`\n]+`)', text)):
        if i % 2:
            out.append(f'<code>{part[1:-1]}</code>')
            continue
        at = 0
        for m in LINK.finditer(part):
            out.append(emph(part[at:m.start()]))
            out.append(f'<a href="{href(m.group(2), depth)}">{emph(m.group(1))}</a>')
            at = m.end()
        out.append(emph(part[at:]))
    return ''.join(out)


def inline_md(text, depth=0):
    """One line of record text, escaped and marked up, with no paragraph around it."""
    return inline(html.escape(text.strip(), quote=True), depth)


def first_block(body, depth=0):
    """The first block of a body, whole: a paragraph with every line of it, or a list with
    every item. Split as markdown() splits, on the source, never on the rendered text."""
    blocks = [b for b in re.split(r'\n\s*\n', body.strip('\n')) if b.strip()]
    return markdown(blocks[0], depth) if blocks else ''


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


FONTS_TOKEN = '{fonts}'  # in the style block, replaced by the page's own way to site/fonts/


def load_look(manual):
    """The look, held beside the records: one style block, and the font files it names with
    their licences. Returns (style text, {file name: bytes}). A missing or empty style block,
    or a font the block names that is not there, is a refusal, never a page with no look."""
    look = os.path.join(manual, 'look')
    no_links(manual)  # load_corpus has looked already; this holds when the look is loaded alone
    try:
        with open(os.path.join(look, 'style.css'), encoding='utf-8') as f:
            style = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise RenderError(f'manual/look/style.css: cannot read ({type(e).__name__})')
    if not style.strip():
        raise RenderError('manual/look/style.css: empty')
    if '</style' in style.lower():
        raise RenderError('manual/look/style.css: holds a closing style tag')
    fonts, folder = {}, os.path.join(look, 'fonts')
    try:
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            path = os.path.join(folder, name)
            if name.startswith('.') or not os.path.isfile(path):
                continue
            with open(path, 'rb') as f:
                fonts[name] = f.read()
    except OSError as e:
        raise RenderError(f'manual/look/fonts: cannot read ({e.strerror})')
    # a face never ships bare: each font file needs its face's licence file beside it and the
    # one-line notice that the fonts are under their own licence (the owner's ruling)
    # every file here that is not a licence or the notice is taken as a font, whatever its
    # ending: a list of font endings would let a face of another ending ship bare
    faces = sorted({re.split(r'[-.]', n)[0] for n in fonts
                    if n != 'NOTICE.txt' and not (n.startswith('LICENSE-') and n.endswith('.txt'))})
    for need in [f'LICENSE-{face}.txt' for face in faces] + (['NOTICE.txt'] if faces else []):
        if not fonts.get(need, b'').strip():
            raise RenderError(f'manual/look/fonts/{need}: a font ships without it')
    for name in re.findall(re.escape(FONTS_TOKEN) + r'([^)\s"\']+)', style):
        if not fonts.get(name):
            raise RenderError(f'manual/look/fonts/{name}: named by the style block and not there')
    return style, fonts


def page(site, title, body_html, depth, current=None):
    up = '../' * depth
    rooms = ''.join(f'<li><a href="{up}{rid}.html"'
                    f'{" aria-current=" + chr(34) + "page" + chr(34) if rid == current else ""}>'
                    f'{html.escape(t)}</a></li>' for rid, t in site['room_titles'])
    head_title = html.escape(title)
    style = site['style'].replace(FONTS_TOKEN, f'{up}fonts/')
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="light dark">\n'
            f'<title>{head_title}</title>\n<style>\n{style}</style>\n</head>\n<body>\n'
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
    if not isinstance(line, str) or not line.strip():
        raise RenderError(f'manual/tools/{card["id"]}.toml: runlog gave no caught line')
    parts.append(f'<h2>{CAUGHT_LABEL}</h2>\n<p class="caught">{html.escape(line)}</p>')
    return page(site, card['name'], '\n'.join(parts), depth=1, current=TOOLS_ROOM)


def render_files(corpus, caught=None):
    """Returns {relative path: text, or bytes for a font} for everything the renderer writes."""
    site = dict(corpus['site'])
    site['style'], fonts = corpus['look']
    rooms, cards = corpus['rooms'], corpus['cards']
    site['room_titles'] = [(rid, rooms[rid]['title']) for rid in site['rooms']]
    for c in cards:
        if c['status'] not in ('released', 'building'):
            raise RenderError(f'manual/tools/{c["id"]}.toml: status {c["status"]!r}')
        if not visible(c['what']):
            raise RenderError(f'manual/tools/{c["id"]}.toml: what has no visible text')
    released = [c for c in cards if c['status'] == 'released']
    building = [c for c in cards if c['status'] == 'building']
    if released and caught is None:
        caught = runlog_caught_line()
    cards_ul = ('\n<ul>' + ''.join(f'<li><a href="tools/{c["id"]}.html">{html.escape(c["name"])}'
                                   f'</a>: {inline_md(c["what"])}</li>' for c in released) + '</ul>'
                if released else '')
    # the front page carries only text that exists: each room's title and the first block of
    # its body, then the released cards as the tools room lists them (none released: no list)
    front = '<ul class="rooms">' + ''.join(
        f'<li><a href="{rid}.html">{html.escape(rooms[rid]["title"])}</a>'
        f'{first_block(rooms[rid]["body"])}</li>' for rid in site['rooms']) + '</ul>'
    files = {'site/index.html': page(site, site['title'], front + cards_ul, depth=0)}
    for name, data in fonts.items():
        files[f'site/fonts/{name}'] = data
    for rid in site['rooms']:
        room = rooms[rid]
        body = markdown(room['body'])
        if rid == TOOLS_ROOM:
            body += cards_ul
        if rid == BUILD_ROOM and building:
            body += '\n<ul>' + ''.join(f'<li>{html.escape(c["name"])}: {IN_PROGRESS}</li>'
                                       for c in building) + '</ul>'
        if rid == TERMS_ROOM and corpus['terms']:
            body += '\n<dl>' + ''.join(f'<dt id="term-{t["id"]}">{html.escape(t["term"])}</dt>'
                                       f'<dd>{markdown(t["body"])}</dd>' for t in corpus['terms']) + '</dl>'
        files[f'site/{rid}.html'] = page(site, room['title'], body, depth=0, current=rid)
    for c in released:
        files[f'site/tools/{c["id"]}.html'] = card_page(site, c, caught)
    for rid, name in READERS:
        files[name] = reader_text(corpus['readers'][rid], site['owner'], rid)
    return files


def reader_text(reader, owner, rid):
    """Markdown for README.md / CLAUDE.md: first section a `#` title, the rest `##` headings."""
    sections = reader['sections']
    if not sections:
        raise RenderError(f'manual/readers/{rid}.toml: no sections')
    if rid == 'readme' and not any(OWNER_TOKEN in s.get('body', '') for s in sections):
        raise RenderError(f'manual/readers/{rid}.toml: no {OWNER_TOKEN} signature line')
    out = []
    for i, s in enumerate(sections):
        if 'heading' not in s or 'body' not in s:
            raise RenderError(f'manual/readers/{rid}.toml: section {i + 1} lacks heading or body')
        mark = '#' if i == 0 else '##'
        body = s['body'].strip('\n').replace(OWNER_TOKEN, owner)
        out.append(f'{mark} {s["heading"]}\n\n{body}\n')
    return '\n'.join(out)


def write(files, out, in_place):
    """In place, site/ is wholly derived and is replaced. Under --out, writes only its files."""
    site = os.path.join(out, 'site')
    if os.path.exists(site) and not os.path.isdir(site):
        raise RenderError('site: exists in the output folder and is not a folder')
    try:
        if in_place and os.path.isdir(site):
            shutil.rmtree(site)
        for rel, text in files.items():
            path = os.path.join(out, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if isinstance(text, bytes):
                with open(path, 'wb') as f:
                    f.write(text)
                continue
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    except OSError as e:
        raise RenderError(f'{os.path.relpath(e.filename, out) if e.filename else "output"}: '
                          f'cannot write: {e.strerror}')


def render(manual, out, caught=None, in_place=False):
    files = render_files(load_corpus(manual), caught)
    write(files, out, in_place)
    return files


# ---- self-test: fixture text only; ends with `selftest: PASS` or `selftest: FAIL`.
# Its fixtures are committed under manual/tests/.

FIX = os.path.join(ROOT, 'manual', 'tests')


def refused(manual, out, stub, reason=''):
    """True when the render is refused, and for the reason named when one is given."""
    try:
        render(manual, out, stub)
        return False
    except RenderError as e:
        return reason in str(e)


def selftest_cases(case):
    fixture = load(os.path.join(FIX, 'markdown-fixture.toml'), 'room', ROOT)
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
    plant = markdown(load(os.path.join(FIX, 'link-plant.toml'), 'room', ROOT)['body'])
    case('markup never reaches a link address',
         '<a href="../FIXTURE-*a*-b.md">link with <em>marked</em> text</a>' in plant)

    with tempfile.TemporaryDirectory() as tmp:
        manual = os.path.join(tmp, 'manual')
        shutil.copytree(os.path.join(ROOT, 'manual'), manual,
                        ignore=shutil.ignore_patterns('tests', 'tools'))
        os.makedirs(os.path.join(manual, 'tools'))
        for name in ('card-released', 'card-building'):
            shutil.copy(os.path.join(FIX, f'{name}.toml'), os.path.join(manual, 'tools'))
        calls = []

        def stub(tool, catching=None):
            calls.append((tool, catching))
            return 'no real run yet'

        a, b = os.path.join(tmp, 'a'), os.path.join(tmp, 'b')
        fa = render(manual, a, stub)
        render(manual, a, stub)  # twice into the same place
        fb = render(manual, b, stub)
        def on_disk(path, t):
            with open(path, 'rb') as f:
                return f.read() == (t if isinstance(t, bytes) else t.encode('utf-8'))
        same = fa == fb and all(on_disk(os.path.join(a, p), t) for p, t in fb.items())
        case('render twice: byte-identical', same)
        case('render: no empty file', all(fa.values()))
        case('front page carries the limit line',
             'That it mirrors that work is the owner' in fa['site/index.html'])
        case('README signature reads the owner from site.toml', 'Chad Wallace' in fa['README.md']
             and OWNER_TOKEN not in fa['README.md'])
        page_ = fa.get('site/tools/card-released.html', '')
        case('released card renders every field', all(l in page_ for _, l in CARD_FIELDS)
             and '<em>fixture</em>' in page_ and '&lt;file&gt;' in page_ and CAUGHT_LABEL in page_)
        case('a card\'s what is marked up in the tools room as on its page',
             '<em>fixture</em> tool' in fa['site/tools.html'])
        case('caught line comes from runlog.caught_line with the card\'s catching',
             calls and set(map(repr, calls)) == {repr(('card-released', ['exact', 'absent']))}
             and 'no real run yet' in page_)
        case('building card: absent from tools room, in progress in build room',
             'Fixture building tool' not in fa['site/tools.html']
             and f'Fixture building tool: {IN_PROGRESS}' in fa['site/build.html']
             and 'site/tools/card-building.html' not in fa)

        pages = {p: t for p, t in fa.items() if p.endswith('.html')}
        case('the look: every page carries the one style block and says light and dark',
             pages and all('<style>' in t and '<meta name="color-scheme" content="light dark">' in t
                           and FONTS_TOKEN not in t for t in pages.values()))
        fonts_dir = os.path.join(manual, 'look', 'fonts')
        shipped = {n for n in os.listdir(fonts_dir) if not n.startswith('.')}
        case('the look: every font and licence file is written to site/fonts/, byte for byte',
             shipped and all(open(os.path.join(fonts_dir, n), 'rb').read() == fa.get(f'site/fonts/{n}')
                             for n in shipped))
        case('the look: a font address is the page\'s own way to site/fonts/',
             'url(fonts/' in fa['site/index.html'] and 'url(../fonts/' not in fa['site/index.html']
             and 'url(../fonts/' in page_ and 'url(fonts/' not in page_)
        case('the look: the current room is marked in the nav, once, and a card marks the tools room',
             fa['site/build.html'].count('aria-current="page"') == 1
             and f'href="{BUILD_ROOM}.html" aria-current="page"' in fa['site/build.html']
             and f'href="../{TOOLS_ROOM}.html" aria-current="page"' in page_
             and 'aria-current="page"' not in fa['site/index.html'])
        corpus_now = load_corpus(manual)
        want_rows = ''.join(f'<li><a href="{rid}.html">{html.escape(corpus_now["rooms"][rid]["title"])}</a>'
                            f'{first_block(corpus_now["rooms"][rid]["body"])}</li>'
                            for rid in corpus_now['site']['rooms'])
        case('the front page lists the rooms and the released cards, from text that exists',
             fa['site/index.html'].split('<main>')[1].count('<li>')
             == len(corpus_now['site']['rooms']) + 1
             and 'tools/card-released.html' in fa['site/index.html']
             and f'<ul class="rooms">{want_rows}</ul>' in fa['site/index.html'])
        case('a first block is whole: every line of a paragraph, every item of a list, tags closed',
             first_block('line one\nline two\nline three\n\nsecond block')
             == '<p>line one\nline two\nline three</p>'
             and first_block('- one\n- two\n\nafter') == '<ul><li>one</li><li>two</li></ul>'
             and first_block('\n\n   \n\nreal words\r\nmore') .startswith('<p>real words')
             and first_block('\n \n') == '')
        case('the caught line is marked for the look', '<p class="caught">no real run yet</p>' in page_)
        # the front page's use of first_block, on a room whose first block runs over three lines
        long_first = os.path.join(tmp, 'long-first')
        shutil.copytree(manual, long_first)
        room_file = os.path.join(long_first, 'rooms', f'{BUILD_ROOM}.toml')
        with open(room_file, encoding='utf-8') as f:
            room_text = f.read()
        with open(room_file, 'w', encoding='utf-8') as f:
            f.write(room_text.replace("body = '''\n", "body = '''\nFIXTURE line one\nline two\nline three\n\n", 1))
        flong = render(long_first, os.path.join(tmp, 'long-first-out'), stub)
        case('the front page carries a room\'s first block whole when it runs over several lines',
             '<p>FIXTURE line one\nline two\nline three</p></li>' in flong['site/index.html'])
        bare = os.path.join(tmp, 'bare')
        shutil.copytree(manual, bare)
        os.remove(os.path.join(bare, 'tools', 'card-released.toml'))
        fbare = render(bare, os.path.join(tmp, 'bare-out'), stub)
        case('no released card: the front page has no empty list',
             '<ul></ul>' not in fbare['site/index.html'] and '<ul></ul>' not in fbare['site/tools.html']
             and fbare['site/index.html'].count('<ul') == 2)  # the nav and the rooms
        for label, breaker, needle in (
                ('an empty style block', lambda d: open(os.path.join(d, 'look', 'style.css'), 'w').close(),
                 'manual/look/style.css: empty'),
                ('a missing style block', lambda d: os.remove(os.path.join(d, 'look', 'style.css')),
                 'manual/look/style.css: cannot read'),
                ('a closing style tag in the style block, in any case',
                 lambda d: open(os.path.join(d, 'look', 'style.css'), 'a').write('\n</STYLE >\n'),
                 'holds a closing style tag'),
                ('a face with no licence file beside it',
                 lambda d: os.remove(os.path.join(d, 'look', 'fonts', sorted(
                     n for n in shipped if n.startswith('LICENSE-'))[0])), 'a font ships without it'),
                ('a face of an ending no list names, with no licence file',
                 lambda d: open(os.path.join(d, 'look', 'fonts', 'FIXTUREFACE-400.eot'), 'wb').write(b'fixture'),
                 'LICENSE-FIXTUREFACE.txt: a font ships without it'),
                ('a face file with no hyphen and no licence file',
                 lambda d: open(os.path.join(d, 'look', 'fonts', 'FIXTUREMONO.ttf'), 'wb').write(b'fixture'),
                 'LICENSE-FIXTUREMONO.txt: a font ships without it'),
                ('a licence file that is white space',
                 lambda d: open(os.path.join(d, 'look', 'fonts', sorted(
                     n for n in shipped if n.startswith('LICENSE-'))[0]), 'w').write(' \n\t\n'),
                 'a font ships without it'),
                ('fonts with no notice of their own licence',
                 lambda d: os.remove(os.path.join(d, 'look', 'fonts', 'NOTICE.txt')),
                 'NOTICE.txt: a font ships without it'),
                ('a fonts folder that cannot be read',
                 lambda d: os.chmod(os.path.join(d, 'look', 'fonts'), 0o000), 'manual/look/fonts: cannot read'),
                ('a style block that is a link',
                 lambda d: (os.rename(os.path.join(d, 'look', 'style.css'), os.path.join(d, 'look', 'kept.css')),
                            os.symlink('kept.css', os.path.join(d, 'look', 'style.css'))),
                 'manual/look/style.css: a link'),
                ('a fonts folder that is a link',
                 lambda d: (os.rename(os.path.join(d, 'look', 'fonts'), os.path.join(d, 'look', 'kept')),
                            os.symlink('kept', os.path.join(d, 'look', 'fonts'))),
                 'manual/look/fonts: a link'),
                ('a link in the fonts folder',
                 lambda d: os.symlink('NOTICE.txt', os.path.join(d, 'look', 'fonts', 'FIXTURE-link.txt')),
                 'FIXTURE-link.txt: a link, not a file or folder'),
                ('a room record that is a link',
                 lambda d: (os.rename(os.path.join(d, 'rooms', 'build.toml'), os.path.join(d, 'kept.toml')),
                            os.symlink(os.path.join('..', 'kept.toml'), os.path.join(d, 'rooms', 'build.toml'))),
                 'manual/rooms/build.toml: a link'),
                ('a records folder that is a link',
                 lambda d: (os.rename(os.path.join(d, 'terms'), os.path.join(d, 'kept-terms')),
                            os.symlink('kept-terms', os.path.join(d, 'terms'))),
                 'manual/terms: a link'),
                ('a link in a folder the renderer never reads',
                 lambda d: (os.makedirs(os.path.join(d, 'FIXTURE-other')),
                            os.symlink('nowhere', os.path.join(d, 'FIXTURE-other', 'FIXTURE-broken'))),
                 'manual/FIXTURE-other/FIXTURE-broken: a link'),
                ('a font the style block names that is not there',
                 lambda d: os.remove(os.path.join(d, 'look', 'fonts', sorted(
                     n for n in shipped if n.endswith('.ttf'))[0])), 'named by the style block and not there')):
            broken = os.path.join(tmp, 'look-' + re.sub(r'\W+', '-', label))
            shutil.copytree(manual, broken)
            breaker(broken)
            try:
                render(broken, os.path.join(tmp, 'never'), stub)
                case(f'the look: {label} is refused', False)
            except RenderError as e:
                case(f'the look: {label} is refused', needle in str(e) and tmp not in str(e))
            finally:
                if not os.path.islink(os.path.join(broken, 'look', 'fonts')):
                    os.chmod(os.path.join(broken, 'look', 'fonts'), 0o755)

        keep = os.path.join(tmp, 'keep')
        os.makedirs(os.path.join(keep, 'site'))
        with open(os.path.join(keep, 'site', 'kept.txt'), 'w') as f:
            f.write('kept\n')
        render(manual, keep, stub)
        case('--out deletes nothing it did not write', os.path.isfile(os.path.join(keep, 'site', 'kept.txt')))

        empty = lambda tool, catching=None: ''
        case('an empty caught line is refused', refused(manual, os.path.join(tmp, 'e'), empty))

        shutil.copy(os.path.join(FIX, 'card-bad-id.toml'), os.path.join(manual, 'tools'))
        case('an id that is not lower-case letters, digits and hyphens is refused',
             refused(manual, os.path.join(tmp, 'f'), stub)
             and not os.path.exists(os.path.join(tmp, 'f', 'site', 'FIXTURE-climbed-out.html')))
        os.remove(os.path.join(manual, 'tools', 'card-bad-id.toml'))

        site_toml = os.path.join(manual, 'site.toml')
        shutil.copy(site_toml, site_toml + '.kept')
        shutil.copy(os.path.join(FIX, 'site-empty-owner.toml'), site_toml)
        case('an empty owner is refused', refused(manual, os.path.join(tmp, 'g'), stub, 'owner is empty'))
        with open(site_toml, encoding='utf-8') as f:
            text = f.read()
        with open(site_toml, 'w', encoding='utf-8') as f:
            f.write(text.replace('owner = ""', 'owner = "   "'))
        case('an owner of white space is refused', refused(manual, os.path.join(tmp, 'h'), stub, 'owner is empty'))
        shutil.copy(os.path.join(FIX, 'site-zero-width-owner.toml'), site_toml)
        case('an owner with no visible character is refused', refused(manual, os.path.join(tmp, 'i'), stub, 'owner is empty'))
        shutil.copy(os.path.join(FIX, 'site-hangul-filler-owner.toml'), site_toml)
        case('an owner of a blank-looking letter (U+3164) is refused',
             refused(manual, os.path.join(tmp, 'k'), stub, 'owner is empty'))
        shutil.move(site_toml + '.kept', site_toml)

        for fixture, folder, name in (('room-empty-how-it-runs', 'rooms', 'how-it-runs'),
                                      ('room-index', 'rooms', 'index'),
                                      ('card-all-empty', 'tools', 'card-all-empty')):
            target = os.path.join(manual, folder, f'{name}.toml')
            kept = open(target, 'rb').read() if os.path.isfile(target) else None
            shutil.copy(os.path.join(FIX, f'{fixture}.toml'), target)
            why, reason = {
                'room-empty-how-it-runs': ('a room body with no visible text is refused, though its '
                                           'term list would fill the page', 'body has no visible text'),
                'room-index': ('a room id of index is refused: it would replace the front page',
                               'reserved for the front page'),
                'card-all-empty': ('a card whose what has no visible text is refused',
                                   'what has no visible text')}[fixture]
            case(why, refused(manual, os.path.join(tmp, f'j-{name}'), stub, reason))
            if kept is None:
                os.remove(target)
            else:
                with open(target, 'wb') as f:
                    f.write(kept)

        blocked = os.path.join(tmp, 'blocked')
        os.makedirs(blocked)
        open(os.path.join(blocked, 'site'), 'w').close()
        try:
            render(manual, blocked, stub)
            case('a site that is a file under --out is a named error', False)
        except RenderError as e:
            case('a site that is a file under --out is a named error', str(e).startswith('site: '))

        readme = os.path.join(manual, 'readers', 'readme.toml')
        with open(readme, encoding='utf-8') as f:
            text = f.read()
        with open(readme, 'w', encoding='utf-8') as f:
            f.write(text.replace(OWNER_TOKEN, 'someone'))
        case('README without the owner signature is refused', refused(manual, os.path.join(tmp, 'c'), stub))
        os.remove(site_toml)
        case('a corpus with no site.toml is refused', refused(manual, os.path.join(tmp, 'd'), stub))


def selftest():
    results = []

    def case(name, ok):
        results.append(bool(ok))
        print(f'{"PASS" if ok else "FAIL"} · {name}')

    try:
        selftest_cases(case)
    except Exception as e:  # a corpus or fixture that cannot be read: can't tell, said, never silent
        # never a machine path: a RenderError names files relative to the repository, and any
        # other error is named by its type and the fixture's file name alone
        what = str(e) if isinstance(e, RenderError) else os.path.basename(getattr(e, 'filename', '') or '')
        print(f'CAN\'T TELL · the self-test could not run its cases ({type(e).__name__}'
              f'{": " + what if what else ""})')
        print('selftest: FAIL')
        return 2
    ok = all(results)
    print(f'selftest: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


def main(argv):
    args = [a for a in argv if a != '--no-log']  # accepted and ignored: the renderer writes no log
    if args == ['--selftest']:
        return selftest()
    out, in_place = ROOT, True
    if len(args) == 2 and args[0] == '--out':
        out, in_place = os.path.abspath(args[1]), False
    elif args:
        print('usage: render.py [--out DIR] [--selftest] [--no-log]', file=sys.stderr)
        return 2
    try:
        files = render(os.path.join(ROOT, 'manual'), out, in_place=in_place)
    except RenderError as e:
        print(f'CAN\'T RENDER: {e}', file=sys.stderr)
        return 2
    print(f'wrote {len(files)} files')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
