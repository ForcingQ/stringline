# SPEC · the corpus: one source, held as data

**Ground truth.** Two earlier manuals of the owner's keep their text as data apart from the pages that show it; one holds typed records with a card per tool, the other markdown with headings. Neither feeds its repository's README or an agent's instructions (read at the second session, not re-run); that is new here. Today this repository's README and CLAUDE.md are hand-written.

**In.** A folder of records, one record per file; a renderer that writes the manual site, README.md and CLAUDE.md from it; the check that the three stay equal to it; the definitions a stranger asked for. **Out.** The look (session 5). **Deferred.** A second language; an assistant reader.

## Shape

- **Folder `manual/`.** `site.toml` (`title`; `owner`, the owner's name for the signature line; `limit`, the manual's limit line, text below; `rooms`, the ordered list of room ids) · `rooms/<id>.toml` (one page each: *tools*, *build*, *how-it-runs*) · `tools/<id>.toml` (one card per tool; keys in [SPEC-card.md](SPEC-card.md)) · `terms/<id>.toml` (one definition each) · `readers/readme.toml` and `readers/claude.toml` (the two derived files, as ordered sections).
- **Format: TOML.** *Why:* typed records read by key with the standard library (`tomllib`), holding prose in multi-line strings; cards and check scope derive by key, where a markdown-with-headings source would need a hand-kept card list. The bodies are markdown, in a named subset below.
- **One record per file.** *Why:* every file fits on one screen, and a record is the unit a check names when it fails. An `id` is the file name without `.toml`.
- **Keys.** A room: `id`, `title`, `body`. A term: `id`, `term` (the phrase as used), `body`. A reader: `id`, `sections` (an array of `{heading, body}`). The site file and the cards have their own keys. Any key outside its record's list is a fault the resolution check names.
- **Markdown subset for bodies**, rendered by our own small function with a fixture that shows every element: paragraphs, `[text](path)` links, `#term:<id>` links, emphasis with `*`, inline code, bulleted lists. Anything else is written as it is, with HTML's special characters (`& < > " '`) escaped in every body before markup is applied. A page is one HTML file: the title, a list of the rooms as links, the body, and a footer carrying the limit line. *Why:* the standard library has no markdown renderer, and a whole one is not needed for one-screen pages.
- **Links** in any body are paths relative to the repository root, or `#term:<id>`; both must resolve ([SPEC-guard.md](SPEC-guard.md), check 2).
- **The how-it-runs room** holds the terms and points at [OPEN-PROTOCOL.md](OPEN-PROTOCOL.md) and [DECISIONS.md](DECISIONS.md); those two files stay the one text of how the work runs. *Why:* two hand-kept copies of the same rules would drift.

## The text the records carry at first (the owner approves it with this spec; lane A copies, never writes)

- **Limit line:** *The earlier work this recreates is not shown. That it mirrors that work is the owner's claim, dated. What you can check: whether each tool fires on its planted fault, and what its run log shows.*
- **lane:** *One AI agent session with one aim and its own finished list, run beside other lanes. Anything it finds outside its aim gets a home elsewhere and is not pursued there.*
- **the finished list:** *The numbered list a session or lane writes before work starts: what will be true when it is done, and how each line is proven, by a command, by the owner's words, or by someone else looking.*
- **a planted fault:** *A fault put deliberately where a real one would arrive, to show that a check fires on it. A check is not trusted until it has.*
- **the one gotcha:** *The single thing most likely to bite a first user of a tool, stated on its card.*
- **the checker:** *The first tool. It compares each quote of a person's words against what that person typed, and says exact, corrected, absent or can't check.*
- **measure, never remember:** *A session reads the actual state of the files and the repository before stating it, rather than trusting what an earlier session said.*
- **README.md and CLAUDE.md:** their text today moves into the reader records verbatim, one section per heading of the file as it stands (the text above the first heading is the first section, with the file's title as its heading); any change of wording is a stop for the lane, not a choice. The first use of each term's phrase in each room links to it (kept by hand; check 2 proves links resolve, not that every use is linked).

## Readers

- **`render.py`** reads `manual/` and writes, in place or into a folder given with `--out <dir>`, `site/` (static HTML: a front page with the limit line, one page per room, one page per released card; plain and valid, the look being a later tier), README.md and CLAUDE.md. It never invents text: everything it writes is a record's field, a derived list (the released cards, the building ones by name) or a derived line (each card's "what it has caught", from `tools/runlog.py`).
- **README.md and CLAUDE.md are written by the renderer**; editing either by hand is a fault check 3 names. The README's signature line comes from `site.toml`'s `owner`, so a regenerated README cannot drop the owner's name. *Why:* the intent commits to one source for the site, the README and the agent's brief, checked on every change.
- **Every commit that touches `manual/`, `runs/` or `render.py` carries the re-rendered `site/`, README.md and CLAUDE.md**; after each merge the session lead re-renders and commits on main before the next merge. *Why:* the derived files go stale with every card, row or merge, and check 3 is red until someone re-renders.
- **Check 3 (derived readers)** is built with the renderer, by the same lane: `render.py --out <scratch>`, compared to the working files byte for byte, touching nothing in the tree (a reviewer's in-place stand-in erased a hand edit and read green); red names the file and the first differing line. Twin: a render that writes nothing, or an empty page, is red.

## Done when

- `python3 render.py` on the committed corpus writes `site/`, README.md and CLAUDE.md, and running it twice changes nothing (byte-identical).
- Check 3 is green on the committed tree, red on a hand-edited README (fixture), red on an empty render (twin).
- Every record parses; a fixture record with a key outside its list, and one with a dangling `#term:` link, each make check 2 red naming the file.
- The markdown fixture renders every element of the subset, and an element outside it comes through escaped.
- The six terms and the limit line exist as records with the text above; the README's signature line reads the owner's name after regeneration.

**Not proven by the above:** that the prose is clear (the stranger read at each close) or that the site looks finished (session 5).
