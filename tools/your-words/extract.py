#!/usr/bin/env python3
"""extract: a person's typed messages, out of a Claude Code session record.

How it is fired: by hand, python3 tools/your-words/extract.py <record.jsonl>
[more] --out <file> [--times <file>] (a real run, one row in runs/ under the
tool id your-words); with --planted "<what, by whom>" for a plant; with
--no-log for no row; its self-test with --selftest.

The failure that earned it: a curated words file that had silently corrected a
misspelling the person typed, read as if it were the source.

It is the second half of the your-words tool (SPEC-extractor.md): it writes
the checker's plain-text shape, one typed message per block, white space kept
exactly. It produces and catches nothing: it never exits 1, and its row's
caught is always empty. When the run log refuses its row (a real run over
fixtures), it reads can't read, exits 2 and writes nothing.

A timestamp is read only in the shape the records carry: ISO 8601 at UTC with
milliseconds, ending Z (2026-01-01T10:00:00.000Z). A space for the T, the
compact form, an offset, a week date, or no zone is another shape: can't read.
--out and --times are refused when a file is there, the folder is missing,
both name one file, or the folder lies inside the repository or any of its
worktrees (folder identity, git's top level, git's worktree list). Limit: a
separate clone of the repository is another repository, and is not refused.

Named limits. The table of harness tags below is hand-kept: a tag or marker
outside it, a short paste the harness did not tag, a prompt an agent wrote
into a seat's own record, and a summary the harness wrote after compaction
each pass as typed. A git that exits 0 listing no worktree is trusted. A copy
of the tool outside any repository refuses every --out (the worktree check
cannot be made). A refusal line names the repository's own folder on the
person's own screen, never in a file. A lone surrogate anywhere in a typed
event, even inside a paste that would be removed, makes the whole event can't
read. Anything unhandled is caught at the entry point: one line under could
not see, exit 2, no row, no output left. Words a person types as a slash command or its arguments
go with the command. One rule reads both tags: after a tag's name come
name=value pairs only (a value in double or single quotes, or one bare word).
A word after an opening tag's name (<name block>) is prose, as it is in a
closing tag, so that is no opening tag, at a line's start or inside a line: it
once opened a block, and everything typed from there to the next real closing
tag of that name was removed, unseen and uncounted. Limits, named and not
mended: an opening tag that is not that shape is not a tag here, so a paste
under one stays in the output whole and is NOT counted as left whole (count 0);
two such shapes are a > inside a single-quoted value on the opening tag, which
ends the tag early where it is looked for, and a loose apostrophe before a
single-quoted id. After any real run, look for a tag line left in the output.
A block typed at a line's start with its closing tag is
removed, as the harness's would be; a tag typed mid-line with no attribute, or
with no closing tag, is kept. When the opening tag has an id, removal runs to
the first closing tag that carries the same id, as a real record's paste does
(every block measured in this build's own records closes with its opening id),
so a closing tag with another id, or none, inside such a block is body; when
the opening tag has no id, to the first closing tag, bare or with attributes.
No fixture held the real shape until a real run let six pasted blocks through
as typed. A tag,
opening or closing, sits on one line, and a > inside a double-quoted attribute
does not end it; a tag broken across lines is not a tag here and is kept. In a
closing tag only name=value pairs count as attributes: prose after the name,
or a bare word (</name hidden>), closes nothing, and that block is kept whole
where a reader can see it, never cut short. Every block left whole (an
opening tag that would have opened a block, with no closing tag that matches)
is counted in the summary line and the row as blocks left whole, so a reader
need not search the output for one; a tag's name typed at a line's start with
nothing closing it is counted there too. Limit: --out and --times
are compared as one name after Unicode composition and then case folding, not
composed again after; a few Greek letters with two accents (U+0390, U+03B0 and
their kin) against their capitals are one file to some file systems and two
names here. Such a pair is not refused up front; the second write fails and is
caught: one line, exit 2, nothing left written. A span quoted back from
inside a message is not counted, only a whole message's text.
Python 3.11 or later, standard library only, plus git.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)  # the checker beside it, also under python3 -I
import runlog  # noqa: E402  (imported by its path: tools/ holds no package)
import your_words  # noqa: E402  (the checker: one rule for a blank line and a block)

TOOL = "your-words"
OWN_FILES = ["tools/your-words/your_words.py", "tools/your-words/extract.py",
             "tools/runlog.py"]
TAGS = ("pasted_content", "system-reminder", "command-name", "command-message",
        "command-args", "local-command-stdout", "local-command-stderr",
        "local-command-caveat", "task-notification", "teammate-message",
        "bash-input", "bash-stdout", "bash-stderr")
MARKER = "[Request interrupted"
TYPED_SOURCES = ("typed", "queued")
COUNTS = ("messages", "later", "nothing_typed", "harness_skipped", "events_skipped",
          "parts_skipped", "edge_blank_dropped", "inner_blank_kept", "blocks_left_whole",
          "cant_read")


class CantRead(Exception):
    """One line or event that could not be read."""


# ---------------------------------------------------------------- reading

STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


def parse_stamp(value):
    """A timestamp in the records' own shape, parsed as a UTC date; CantRead else."""
    if not isinstance(value, str):
        raise CantRead("no timestamp")
    if not STAMP.fullmatch(value):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?", value):
            raise CantRead("timestamp without a zone")
        raise CantRead("timestamp of another shape")
    try:
        return datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise CantRead("timestamp of another shape") from None


TAG_REST = re.compile(r'''(?:"[^"\n]*"|[^>"\n])*>''')  # the rest of a tag, to its >

# after a closing tag's name: name=value pairs only (a value quoted or one bare
# word), then >. Prose after the name is not an attribute, so it closes nothing.
CLOSER_REST = (r'''(?:[ \t]+[A-Za-z_][\w:.-]*=(?:"[^"\n]*"|'[^'\n]*'|[^\s"'<>=]+))*'''
               r"[ \t]*>")
# the same rule for an opening tag: after its name, name=value pairs only
OPENER_PAIRS = re.compile(CLOSER_REST[:-1])  # the closing tag's pairs, without the final >

# a tag's attributes, read pair by pair, so a quoted value is taken whole and
# the letters id= inside another attribute's value are never an id
ATTR = re.compile(r'''([A-Za-z_][\w:.-]*)=(?:"([^"\n]*)"|'([^'\n]*)'|([^\s"'<>=]+))''')
QUOTED = re.compile(r'"[^"\n]*"' r"|'[^'\n]*'")


def tag_id(attrs):
    """The value of the attribute named exactly id (the first, if two), or None."""
    i = 0
    while i < len(attrs):
        if attrs[i] in " \t":
            i += 1
            continue
        m = ATTR.match(attrs, i)
        if m:
            if m.group(1) == "id":
                return next(g for g in m.groups()[1:] if g is not None)
            i = m.end()
            continue
        q = QUOTED.match(attrs, i)  # a loose quoted run is stepped over whole
        if q:
            i = q.end()
            continue
        j = i
        while j < len(attrs) and attrs[j] not in " \t\"'":
            j += 1
        i = max(j, i + 1)
    return None


def remove_blocks(text):
    """(text with the harness's blocks removed, [removed pasted_content bodies],
    how many blocks were left whole because no closing tag matched)."""
    pastes, whole = [], 0
    names = "|".join(re.escape(t) for t in TAGS)
    opener = re.compile(r"<(" + names + r")([ >])")
    pos = 0
    while True:
        m = opener.search(text, pos)
        if not m:
            break
        name, start = m.group(1), m.start()
        line_start = text.rfind("\n", 0, start) + 1
        at_line_start = text[line_start:start].strip() == ""
        # a tag sits on one line; a > inside a quoted attribute does not end it
        opened = TAG_REST.match(text, m.end(1))
        tag_end = opened.end() - 1 if opened else -1
        # one rule for both tags: after the name, only name=value pairs. A word after an
        # opening tag's name (<name block>) is prose, as it is in a closing tag, so that is
        # no opening tag, at a line's start or inside a line, and nothing after it is removed
        # on its account.
        if tag_end < 0 or not OPENER_PAIRS.fullmatch(text, m.end(1), tag_end):
            pos = m.end(1)
            continue
        has_attr = text[m.end(1):tag_end].strip() != ""
        # a closing tag is looked for after the opening tag, never inside it; a
        # longer name is no closer. When the opening tag has an id, only a closing
        # tag with that id closes it (a real record repeats a paste's id there):
        # one with another id, or none, is part of the body. With no id on the
        # opening tag, the first closing tag closes it, bare or with attributes.
        closer = None
        if tag_end >= 0:
            want = tag_id(text[m.end(1):tag_end])
            for c in re.compile(r"</" + re.escape(name) + CLOSER_REST
                                ).finditer(text, tag_end + 1):
                if want is None or tag_id(c.group(0)[len(name) + 2:-1]) == want:
                    closer = c
                    break
        close = closer.start() if closer else -1
        if tag_end < 0 or close < 0 or not (at_line_start or has_attr):
            if tag_end >= 0 and close < 0 and (at_line_start or has_attr):
                whole += 1  # it would have opened a block; nothing closed it
            pos = m.end(1)
            continue
        end = closer.end()
        if name == "pasted_content":
            pastes.append(text[tag_end + 1:close])
        line_end = text.find("\n", end)
        line_end = len(text) if line_end < 0 else line_end
        if (text[line_start:start] + text[end:line_end]).strip() == "":
            # the line where the block stood is left empty: drop it whole
            if line_end < len(text):
                text = text[:line_start] + text[line_end + 1:]
            else:
                text = text[:max(line_start - 1, 0)] if line_start else ""
            pos = line_start if line_start <= len(text) else len(text)
        else:
            text = text[:start] + text[end:]
            pos = start
    return text, pastes, whole


def remove_markers(text):
    return "\n".join(line for line in text.split("\n") if not line.startswith(MARKER))


def trim_blank_edges(text):
    """(text, edge blank lines dropped, inner blank lines kept). A final line
    break is the last line's ending, not a blank line: only blank lines count."""
    lines = text.removesuffix("\n").split("\n")
    dropped = 0
    while lines and your_words.is_blank(lines[0]):
        lines.pop(0)
        dropped += 1
    while lines and your_words.is_blank(lines[-1]):
        lines.pop()
        dropped += 1
    inner = sum(1 for line in lines if your_words.is_blank(line))
    return "\n".join(lines), dropped, inner


def writable(text):
    """Text that can be written as UTF-8 (no lone surrogate)."""
    try:
        text.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def user_text(event):
    """(raw typed text, [skipped part types]) or CantRead."""
    message = event.get("message")
    if not isinstance(message, dict):
        raise CantRead("a user event with no message")
    if message.get("role") != "user":
        raise CantRead("a user event whose role is missing or not user")
    content = message.get("content")
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        raise CantRead("a user event with no message.content in either shape")
    texts, skipped = [], []
    for part in content:
        if not isinstance(part, dict) or not isinstance(part.get("type"), str):
            raise CantRead("a part without a type")
        if not writable(part["type"]):
            raise CantRead("a part type that is not valid Unicode")
        if part["type"] == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        else:
            skipped.append(part["type"])
    return "".join(texts), skipped


def assistant_texts(event):
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [p["text"] for p in content if isinstance(p, dict) and
            p.get("type") == "text" and isinstance(p.get("text"), str)]


def _is_word_char(ch):
    return ch.isalnum() or ch in "'’"


def recurs(needle, hay):
    """needle as a whole, with a non-word character or the edge on each side."""
    k = hay.find(needle)
    while k >= 0:
        before = hay[k - 1] if k > 0 else ""
        after = hay[k + len(needle)] if k + len(needle) < len(hay) else ""
        if not (before and _is_word_char(before)) and not (after and _is_word_char(after)):
            return True
        k = hay.find(needle, k + 1)
    return False


# ---------------------------------------------------------------- the run

def _rel(path, root):
    real = os.path.realpath(path)
    if runlog.repo_root(real) == root:
        return os.path.relpath(real, root).replace(os.sep, "/")
    return None


def working_trees(root):
    """(the repository's top folder and every worktree git lists for it, None),
    or (None, why) when git is absent or refuses: the check cannot be made, and
    a check that cannot be made never falls back to writing."""
    try:
        out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=root,
                             capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, "git cannot be run here"
    if out.returncode != 0:
        # git's reason, read as bytes: what is not UTF-8 is shown with replacement
        said = (out.stderr.decode("utf-8", "replace").strip().splitlines()
                or ["no reason given"])[0]
        return None, f"git refused to list the worktrees (exit {out.returncode}: {said})"
    listing = os.fsdecode(out.stdout)  # folder names, decoded as the file system's
    tops = [root] + [os.path.realpath(line[len("worktree "):])
                     for line in listing.splitlines() if line.startswith("worktree ")]
    return tops, None


def inside_repository(folder, root):
    """Inside the repository or any of its worktrees, by folder identity and by
    git's own answer, never by path text."""
    real = os.path.realpath(folder)
    tops, why = working_trees(root)
    if tops is None:
        return why  # cannot tell: the caller refuses with this reason
    if runlog.repo_root(real) in tops:
        return True
    here = real
    while True:
        for top in tops:
            try:
                if os.path.samefile(here, top):
                    return True
            except OSError:
                pass
        up = os.path.dirname(here)
        if up == here:
            return False
        here = up


def refuse_target(path, root, what):
    """A reason to refuse an output path, or None."""
    if os.path.lexists(path):
        return f"{what}: a file exists there; nothing is overwritten"
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        return f"{what}: its folder does not exist"
    inside = inside_repository(folder, root)
    if isinstance(inside, str):
        return (f"{what}: {inside}, so whether its folder lies inside a worktree of"
                " the repository cannot be told; nothing is written")
    if inside:
        return (f"{what}: its folder lies inside the repository that holds the tool, or"
                " one of its worktrees; extracted text is private and never lands in"
                " the public tree")
    return None


def refuse_targets(out, times, root):
    """Both output paths checked together, before either file is opened."""
    for path, what in ((out, "--out"), (times, "--times")):
        if path:
            why = refuse_target(path, root, what)
            if why:
                return why
    if times and same_file(out, times):
        return "--out and --times name the same file; nothing is written"
    return None


def same_file(a, b):
    """One file by identity, not by name: the folders by samefile, the names
    folded to one Unicode form (composed and decomposed are one name on some
    file systems) and to one letter case; samefile when either exists."""
    a, b = os.path.realpath(os.path.abspath(a)), os.path.realpath(os.path.abspath(b))
    if os.path.exists(a) or os.path.exists(b):
        try:
            return os.path.samefile(a, b)
        except OSError:
            pass
    try:
        same_folder = os.path.samefile(os.path.dirname(a), os.path.dirname(b))
    except OSError:
        same_folder = os.path.dirname(a) == os.path.dirname(b)

    def name(p):
        return unicodedata.normalize("NFC", os.path.basename(p)).casefold()
    return same_folder and name(a) == name(b)


def extract(records):
    """Read every record; return a dict with the messages, report lines and counts."""
    root = runlog.module_root()
    counts = dict.fromkeys(COUNTS, 0)
    events_skipped, parts_skipped = {}, {}
    names, read, cant, could_not = [], [], [], []
    material = []  # (when, record no, line no, kind, payload, stamp as recorded)
    for rno, path in enumerate(records, 1):
        rel = _rel(path, root)
        name = rel or f"outside the repository (record {rno})"
        names.append(name)
        if rel and rel not in read:
            read.append(rel)
        elif not rel and runlog.OUTSIDE not in read:
            read.append(runlog.OUTSIDE)
        try:
            with open(path, "rb") as fh:
                data = fh.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            why = "not UTF-8" if isinstance(exc, UnicodeDecodeError) else \
                f"unreadable ({type(exc).__name__})"
            cant.append((name, None, why))
            continue
        data = data.removeprefix("﻿")
        for lno, line in enumerate(data.split("\n"), 1):
            if not line.strip():
                continue
            try:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    raise CantRead("not JSON") from None
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise CantRead("no type")
                kind = event["type"]
                if not writable(kind):
                    raise CantRead("an event type that is not valid Unicode")
                if kind not in ("user", "assistant"):
                    events_skipped[kind] = events_skipped.get(kind, 0) + 1
                    continue
                stamp = event.get("timestamp")
                when = parse_stamp(stamp)
                if kind == "assistant":
                    for text in assistant_texts(event):
                        material.append((when, rno, lno, "quoted", text, stamp))
                    continue
                source = event.get("promptSource")
                if source is not None and not isinstance(source, str):
                    raise CantRead("a promptSource that is not a string")
                if event.get("isMeta") is True or (source is not None and
                                                   source not in TYPED_SOURCES):
                    counts["harness_skipped"] += 1
                    continue
                raw, skipped = user_text(event)
                if not writable(raw):
                    raise CantRead("text that is not valid Unicode (a lone surrogate)"
                                   " and cannot be written as UTF-8")
                for t in skipped:
                    parts_skipped[t] = parts_skipped.get(t, 0) + 1
                material.append((when, rno, lno, "user", raw, stamp))
            except CantRead as exc:
                cant.append((name, lno, str(exc)))
    material.sort(key=lambda m: (m[0], m[1], m[2]))
    messages = []  # dicts: text, stamp, record, line, later lists, tie
    for when, rno, lno, kind, payload, stamp in material:
        if kind == "quoted":
            for msg in messages:
                if (when, rno, lno) > msg["key"] and recurs(msg["text"], payload):
                    msg["quoted"].append(stamp)
            continue
        text, pastes, _ = remove_blocks(payload)
        text = remove_markers(text)
        for msg in messages:
            for paste in pastes:
                if recurs(msg["text"], paste):
                    msg["pasted"].append(stamp)
                    break
        if not text.strip():
            counts["nothing_typed"] += 1
            continue
        text, dropped, inner = trim_blank_edges(text)
        counts["edge_blank_dropped"] += dropped
        same = next((m for m in messages if m["text"] == text), None)
        for msg in messages:
            if msg is not same and recurs(msg["text"], text):
                msg["typed"].append(stamp)
        if same is not None:
            same["typed"].append(stamp)
            if when == same["when"]:
                same["tie"].append(f"{names[rno - 1]}:{lno}")
            continue
        counts["inner_blank_kept"] += inner
        tie = [m["where"] for m in messages if m["when"] == when]
        messages.append({"text": text, "stamp": stamp, "when": when, "key": (when, rno, lno),
                         "where": f"{names[rno - 1]}:{lno}",
                         "private": names[rno - 1].startswith(runlog.OUTSIDE),
                         "typed": [], "pasted": [], "quoted": [], "tie": tie})
    counts["messages"] = len(messages)
    # counted over what is written, so the count is the number in the output
    counts["blocks_left_whole"] = sum(remove_blocks(m["text"])[2] for m in messages)
    counts["later"] = sum(len(m["typed"]) + len(m["pasted"]) + len(m["quoted"])
                          for m in messages)
    counts["events_skipped"] = sum(events_skipped.values())
    counts["parts_skipped"] = sum(parts_skipped.values())
    counts["cant_read"] = len(cant)
    outside_cant = {}
    for name, lno, why in cant:
        if name.startswith(runlog.OUTSIDE):
            outside_cant[name] = outside_cant.get(name, 0) + 1
        else:
            could_not.append(f"{name}:{lno}" if lno else f"{name}: {why}")
    for name, n in outside_cant.items():
        could_not.append(f"{name}: {n} line(s) could not be read")
    return {"messages": messages, "counts": counts, "events": events_skipped,
            "parts": parts_skipped, "cant": cant, "read": read, "could_not": could_not}


def later_text(m):
    k = len(m["typed"]) + len(m["pasted"]) + len(m["quoted"])
    times = m["typed"] + m["pasted"] + m["quoted"]
    at = f" at {', '.join(str(t) for t in times)}" if times else ""
    return (f"later: {k} (typed {len(m['typed'])} · pasted {len(m['pasted'])}"
            f" · quoted back {len(m['quoted'])}){at}")


def report(result):
    lines = []
    for n, m in enumerate(result["messages"], 1):
        if m["private"]:
            shown = m["where"]
        else:
            words = m["text"].split()
            shown = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
        tie = f" · tie at one instant with {', '.join(m['tie'])}, kept in record order" \
            if m["tie"] else ""
        lines.append(f"{n} · {m['stamp']} · {shown} · {later_text(m)}{tie}")
    for name, lno, why in result["cant"]:
        lines.append(f"can't read · {name}" + (f":{lno}" if lno else "") + f" · {why}")
    c = result["counts"]

    def by_type(d):
        return ", ".join(f"{k} {d[k]}" for k in sorted(d)) or "none"
    lines.append(f"messages: {c['messages']} · later occurrences: {c['later']} · nothing typed:"
                 f" {c['nothing_typed']} · harness events skipped: {c['harness_skipped']}"
                 f" · other events skipped: {by_type(result['events'])} · parts skipped:"
                 f" {by_type(result['parts'])} · edge blank lines dropped:"
                 f" {c['edge_blank_dropped']} · inner blank lines kept: {c['inner_blank_kept']}"
                 f" · blocks left whole: {c['blocks_left_whole']}"
                 f" · can't read: {c['cant_read']}")
    lines.append("read: " + (", ".join(result["read"]) or "nothing"))
    if result["could_not"]:
        lines.append("could not see: " + "; ".join(result["could_not"]))
    elif not result["messages"]:
        lines.append("could not see: no typed message was found")
    else:
        lines.append("could not see: every line was read (what a person typed outside"
                     " the record is never seen)")
    return lines


def words_file(result):
    return "".join(m["text"] + "\n" + ("\n" if i < len(result["messages"]) - 1 else "")
                   for i, m in enumerate(result["messages"]))


def times_file(result):
    out, block = [], 0
    for m in result["messages"]:
        for _ in your_words.split_blocks(m["text"]):  # as the checker counts blocks
            block += 1
            out.append(f"block {block} · {m['stamp']} · {m['where']} · {later_text(m)}")
    return "".join(line + "\n" for line in out)


def exit_code(result):
    return 2 if result["cant"] or not result["messages"] else 0


def run(records, out, times, planted, no_log, quiet=False):
    """Compute, print the report, write the outputs, then the row. Anything that
    goes wrong is one line under could not see, exit 2, nothing left written."""
    root = runlog.module_root()
    why = refuse_targets(out, times, root)
    if why:
        print(f"refused · {why}")
        return 2
    made = []

    def give_up(why):
        """One line under could not see, exit 2, nothing left written, no row."""
        for p in made:
            try:
                os.remove(p)
            except OSError:
                pass
        print(f"can't read · {why}")
        print(f"could not see: {why}")
        return 2  # never a crash, never 1

    try:
        result = extract(records)
        path, kind = None, "planted" if planted else "real"
        if not quiet:
            for line in report(result):
                print(line)
        try:
            for target, body in ((out, words_file), (times, times_file)):
                if target:
                    with open(target, "x", encoding="utf-8") as fh:
                        made.append(target)
                        fh.write(body(result))
        except (OSError, UnicodeError) as exc:
            detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
            return give_up(f"the output could not be written ({type(exc).__name__}:"
                           f" {detail}); nothing was logged and nothing written")
        if not no_log:
            try:
                path = runlog.write(TOOL, OWN_FILES, kind, planted or "", "person",
                                    result["read"], [], dict(result["counts"]), [],
                                    result["could_not"])
            except (runlog.RunLogError, OSError) as exc:
                detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
                return give_up(f"the run log refused this run's row ({type(exc).__name__}:"
                               f" {detail}); nothing was logged and nothing written" +
                               ("; a run on fixtures is a plant: give --planted"
                                if kind == "real" and isinstance(exc, runlog.RunLogError)
                                else ""))
        if path:
            print(f"logged: {os.path.relpath(path, root)} ({kind})")
        return exit_code(result)
    except Exception as exc:  # the net: any case not handled above
        return give_up(f"{type(exc).__name__}; nothing was logged and nothing written")


# ---------------------------------------------------------------- self-test

TESTS = os.path.join(HERE, "tests", "extract")


def log_folder(path):
    """For a self-test case: the run log writes to a scratch folder, never runs/."""
    import contextlib

    @contextlib.contextmanager
    def pointed():
        saved = runlog.default_folder
        runlog.default_folder = lambda files=None: path
        try:
            yield
        finally:
            runlog.default_folder = saved
    return pointed()


def selftest(no_log):
    import contextlib
    import io
    results, totals, skipped = [], dict.fromkeys(COUNTS, 0), []
    root = runlog.module_root()

    def expect(label, ok, shown=""):
        results.append(bool(ok))
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f" -> {shown}" if shown else ""))

    with tempfile.TemporaryDirectory() as tmp:
        cases = sorted(f for f in os.listdir(TESTS) if f.endswith(".toml"))
        for case in cases:
            with open(os.path.join(TESTS, case), "rb") as fh:
                want = tomllib.load(fh)
            label = case.removesuffix(".toml")
            records = [os.path.join(TESTS, r) for r in want.get("records", [label + ".jsonl"])]
            print(f"     {label}: {', '.join(os.path.basename(r) for r in records)}")
            mode = want.get("mode", "extract")
            if mode == "refuse":
                for name, out, times, reason, scratch_root in refusal_targets(
                        want["targets"], tmp, root):
                    if out is None:
                        skipped.append(f"{label}: {name}: {reason}")
                        print(f"skip {label}: {name}: cannot be built here ({reason})")
                        continue
                    before = [p and os.path.exists(p) and open(p, "rb").read()
                              for p in (out, times)]
                    if scratch_root in ("no-git", "git-refuses", "git-refuses-bytes"):
                        # git off the PATH, or a git that runs and refuses: cannot
                        # tell, refuse, never fall back to writing
                        saved_path = os.environ.get("PATH", "")
                        os.environ["PATH"] = "" if scratch_root == "no-git" else \
                            os.path.join(tmp, scratch_root) + os.pathsep + saved_path
                        try:
                            why = refuse_targets(out, times, root)
                        finally:
                            os.environ["PATH"] = saved_path
                        printed, code = f"refused · {why}" if why else "", 2 if why else 0
                    elif scratch_root:  # a scratch repository and its worktree
                        why = refuse_targets(out, times, scratch_root)
                        printed, code = f"refused · {why}" if why else "", 2 if why else 0
                    else:
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            code = run(records, out, times, "selftest", True, quiet=True)
                        printed = buf.getvalue()
                    after = [p and os.path.exists(p) and open(p, "rb").read()
                              for p in (out, times)]
                    expect(f"{label}: {name} refused for its reason, nothing written",
                           code == 2 and before == after and reason in printed,
                           printed.strip() or f"exit {code}")
                continue
            if mode == "unwritable":
                for name in want["targets"]:
                    runs = os.path.join(tmp, f"runs-{name}")
                    locked = os.path.join(tmp, f"locked-{name}")
                    os.makedirs(runs)
                    os.makedirs(locked)
                    out = os.path.join(tmp if name == "runs-folder" else locked,
                                       f"{name}-typed.txt")
                    os.chmod(runs if name == "runs-folder" else locked, 0o555)
                    try:
                        if os.access(runs if name == "runs-folder" else locked, os.W_OK):
                            skipped.append(f"{label}: {name}: a locked folder is writable"
                                           " here (run as an administrator?)")
                            print(f"skip {label}: {name}: cannot be built here")
                            continue
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf), log_folder(runs):
                            code = run(records, out, None, "selftest", False)
                        printed = buf.getvalue()
                        rows = os.listdir(runs)
                        expect(f"{label}: {name}: one line, exit 2, no row, nothing written",
                               code == 2 and not rows and not os.path.exists(out) and
                               "could not see:" in printed and "Error" in printed,
                               printed.strip().splitlines()[0] if printed.strip() else
                               f"exit {code}")
                    finally:
                        os.chmod(runs, 0o755)
                        os.chmod(locked, 0o755)
                continue
            if mode in ("planted-run", "bad-note"):
                # planted-run: outputs and a row (in a scratch log folder) are written
                # bad-note: the writer refuses the note; one line, exit 2, nothing left
                runs = os.path.join(tmp, f"runs-{label}")
                os.makedirs(runs)
                out = os.path.join(tmp, f"{label}-typed.txt")
                note = "selftest" if mode == "planted-run" else "a note \udcff"
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), log_folder(runs):
                    code = run(records, out, None, note, False)
                printed = buf.getvalue()
                rows = [json.load(open(os.path.join(runs, f), encoding="utf-8"))
                        for f in os.listdir(runs)]
                if mode == "planted-run":
                    ok = (code == want["exit"] and os.path.exists(out) and len(rows) == 1 and
                          all(rows[0]["outcomes"].get(k) == v
                              for k, v in want.get("row", {}).items()))
                else:
                    ok = code == 2 and not rows and not os.path.exists(out)
                ok = ok and all(n in printed for n in want.get("contains", []))
                expect(f"{label}: {mode}", ok, f"exit {code} · {len(rows)} row(s)")
                continue
            if mode == "real-run":
                # a person's real run, logging on, over fixtures: the run log refuses
                # the row; the run reads can't read, exit 2, and writes nothing
                out = os.path.join(tmp, label + "-real.txt")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = run(records, out, None, None, False)
                printed = buf.getvalue()
                for line in printed.splitlines():
                    print(f"       {line}")
                expect(f"{label}: a real run over fixtures reads can't read, exit 2, nothing"
                       " written", code == 2 and not os.path.exists(out) and
                       all(n in printed for n in want.get("contains", [])), f"exit {code}")
                continue
            result = extract(records)
            out = words_file(result)
            for line in report(result):
                print(f"       {line}")
            got = {k: v for k, v in result["counts"].items() if v}
            for k, v in result["counts"].items():
                totals[k] += v
            ok = exit_code(result) == want["exit"]
            ok = ok and all(got.get(k, 0) == v for k, v in want.get("counts", {}).items())
            if "out" in want:
                ok = ok and out == want["out"]
            if "times" in want:
                ok = ok and times_file(result) == want["times"]
            for needle in want.get("contains", []):
                ok = ok and any(needle in line for line in report(result))
            expect(f"{label}: exit {exit_code(result)}", ok,
                   "" if ok else f"{got} · out {out!r}")
            if result["messages"]:
                lines_t = len(times_file(result).splitlines())
                blocks = len(your_words.split_blocks(out))
                expect(f"{label}: times lines match the checker's blocks",
                       lines_t == blocks, f"{lines_t} times lines, {blocks} blocks")
            if want.get("feed_checker"):
                path = os.path.join(tmp, label + "-typed.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(out)
                page = os.path.join(TESTS, want["feed_checker"])
                lines, counts, _, _, _, _ = your_words.check([page], path)
                for line in lines:
                    print(f"       {line}")
                expect(f"{label}: its output fed to the checker reads exact",
                       counts["exact"] >= 1 and counts["exact"] == sum(
                           counts[k] for k in ("exact", "corrected", "absent", "cant_check")))
    passed = bool(results) and all(results)
    print(f"{sum(results)}/{len(results)} fixtures" +
          (f" · {len(skipped)} could not be built on this machine (not counted as passed)"
           if skipped else ""))
    if not no_log:
        path = runlog.write(TOOL, OWN_FILES, "planted", "selftest", "selftest", ["fixture"],
                            [], totals, [], [])
        print(f"logged: {os.path.relpath(path, root)} (planted)")
    print("selftest: PASS" if passed else "selftest: FAIL")
    return 0 if passed else 1


def refusal_targets(targets, tmp, root):
    """Each named way of pointing an output at a place it must refuse, built here:
    (name, out, times, the reason it must print, a scratch root or None). A target
    this machine cannot build comes back with out None and why."""
    out = []
    inside = "inside the repository that holds the tool"
    for name in targets:
        if name == "existing":
            target = os.path.join(tmp, "existing.txt")
            if not os.path.exists(target):
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write("already here\n")
            out.append((name, target, None, "a file exists there", None))
        elif name == "no-folder":
            out.append((name, os.path.join(tmp, "no-such-folder", "typed.txt"), None,
                        "its folder does not exist", None))
        elif name == "same-path":
            p = os.path.join(tmp, "same.txt")
            out.append((name, p, p, "name the same file", None))
        elif name == "same-path-other-case":
            out.append((name, os.path.join(tmp, "Same-Case.txt"),
                        os.path.join(tmp, "same-case.txt"), "name the same file", None))
        elif name == "same-path-composed-decomposed":
            composed = unicodedata.normalize("NFC", "FIXTURE-caf\u00e9.txt")
            decomposed = unicodedata.normalize("NFD", "FIXTURE-caf\u00e9.txt")
            out.append((name, os.path.join(tmp, composed), os.path.join(tmp, decomposed),
                        "name the same file", None))
        elif name in ("git-refuses", "git-refuses-bytes"):
            fake = os.path.join(tmp, name)
            os.makedirs(fake, exist_ok=True)
            said = ("fatal: a fixture git that always refuses" if name == "git-refuses"
                    else "fatal: \\377\\376 not text")  # bytes that are not UTF-8
            with open(os.path.join(fake, "git"), "w", encoding="utf-8") as fh:
                fh.write(f"#!/bin/sh\nprintf '{said}\\n' >&2\nexit 128\n")
            os.chmod(os.path.join(fake, "git"), 0o755)
            out.append((name, os.path.join(tmp, f"{name}-typed.txt"), None,
                        "git refused to list the worktrees (exit 128: fatal: " +
                        ("a fixture" if name == "git-refuses" else "\ufffd\ufffd not text"),
                        name))
        elif name == "no-git":
            out.append((name, os.path.join(tmp, "no-git-typed.txt"), None,
                        "git cannot be run here", "no-git"))
        elif name == "inside":
            out.append((name, os.path.join(root, "FIXTURE-extracted.txt"), None, inside, None))
        elif name == "link":
            link = os.path.join(tmp, "link-to-repository")
            if not os.path.lexists(link):
                os.symlink(root, link)
            out.append((name, os.path.join(link, "FIXTURE-extracted.txt"), None, inside, None))
        elif name == "case":
            # tools/ always has letters to flip, whatever the clone's folder is named
            flipped = os.path.join(root, "TOOLS")
            if os.path.isdir(flipped) and os.path.samefile(flipped, os.path.join(root, "tools")):
                out.append((name, os.path.join(flipped, "FIXTURE-extracted.txt"), None,
                            inside, None))
            else:
                out.append((name, None, None, "this file system tells letter case apart,"
                            " so no other-case path names the repository", None))
        elif name == "alias":
            alias = "/System/Volumes/Data" + root
            if os.path.isdir(alias) and os.path.samefile(alias, root):
                out.append((name, os.path.join(alias, "FIXTURE-extracted.txt"), None,
                            inside, None))
            else:
                out.append((name, None, None, "no data-volume alias of the repository"
                            " exists on this machine", None))
        elif name == "worktree":
            repo = os.path.join(tmp, "scratch-repository")
            tree = os.path.join(tmp, "scratch-worktree")
            git = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]
            subprocess.run(git + ["init", "-q", repo], check=True)
            subprocess.run(git + ["-C", repo, "commit", "-q", "--allow-empty", "-m", "fixture"],
                           check=True)
            subprocess.run(git + ["-C", repo, "worktree", "add", "-q", "--detach", tree],
                           check=True)
            out.append((name, os.path.join(tree, "FIXTURE-extracted.txt"), None, inside,
                        os.path.realpath(repo)))
    return out


def main(argv):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass  # a replaced stdout (the self-test's) keeps its own rule
    try:
        return _main(argv)
    except Exception as exc:  # the net: never a traceback, never 1
        print(f"could not see: {type(exc).__name__}")
        return 2


def _main(argv):
    ap = argparse.ArgumentParser(prog="extract.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="It cannot see what a person typed outside the"
                                 " records it is given, nor a paste the harness did not tag.")
    ap.add_argument("records", nargs="*", help="session records (.jsonl), in order")
    ap.add_argument("--out", help="the words file to write (refused inside the repository)")
    ap.add_argument("--times", help="one line per block: its time, record and line")
    ap.add_argument("--planted", metavar="NOTE", help="log a planted row: what, by whom")
    ap.add_argument("--no-log", action="store_true", help="write no row")
    ap.add_argument("--selftest", action="store_true", help="run the synthetic fixtures")
    args = ap.parse_args(argv)
    if args.selftest:
        try:
            return selftest(args.no_log)
        except Exception as exc:  # a crash is a failure, never a silent end
            print(f"FAIL self-test crashed: {type(exc).__name__}: {exc}")
            print("selftest: FAIL")
            return 1
    if not args.records or not args.out:
        print("can't read: give one or more records and --out <file>")
        return 2
    if args.planted is not None and not args.planted.strip():
        print("can't read: --planted needs a note saying what was planted and by whom")
        return 2
    return run(args.records, args.out, args.times, args.planted, args.no_log)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
