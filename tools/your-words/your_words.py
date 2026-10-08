#!/usr/bin/env python3
"""your-words: checks quotes of a person's own typed words against what they typed.

How it is fired: by hand, python3 tools/your-words/your_words.py (a real run,
one row in runs/); with --planted "<what, by whom>" for a reviewer's plant (a
planted row); by the workflow as a report with --no-log (no row); its self-test
with --selftest.

The failure that earned it: a checker that filed what it could not check as
not found.

Each quote (*"…"* in markdown, outside code) reads exact, corrected, absent or
can't check, against the typed messages in WORDS.txt (SPEC-your-words.md).
Negations: not, no, never, none, nor, cannot, nothing, nobody, nowhere, neither,
and any word ending in n't, with or without its apostrophe.
Python 3.11 or later, standard library only, plus git.
"""

import argparse
import math
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import runlog  # noqa: E402  (imported by its path: tools/ holds no package)

TOOL = "your-words"
EARNED_BY = "A checker that filed what it could not check as not found."
CATCHING = ["exact", "corrected", "absent", "cant_check"]
OWN_FILES = ["tools/your-words/your_words.py", "tools/your-words/extract.py",
             "tools/runlog.py"]
OPEN, CLOSE, ELLIPSIS = '*"', '"*', "…"
EDGE = ".,;:!?\"'()[]"
CURLY = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                       "“": '"', "”": '"', "„": '"', "‟": '"'})
NEGATIONS = {"not", "no", "never", "none", "nor",
             "cannot", "nothing", "nobody", "nowhere", "neither"}  # the owner's ruling, #51
# "ends in n't, with or without its apostrophe": the apostrophe-less forms are
# listed, because every word ending in "nt" (want, point, present) is not one.
BARE_NT = {"dont", "doesnt", "didnt", "cant", "couldnt", "wont", "wouldnt", "isnt",
           "arent", "wasnt", "werent", "hasnt", "havent", "hadnt", "shouldnt",
           "mustnt", "neednt", "mightnt", "shant", "aint", "darent", "oughtnt"}
HELP = """\
Checks every quote of a person's own typed words on a page against the
messages that person typed, and says, for each quote, one of:
  exact        the words appear, character for character, in one message
  corrected    one word in eight or fewer differs by a typo (two letter edits)
               or a dropped typed word; case, spacing and punctuation are named
  absent       no message holds it, or a negation was changed, dropped or
               skipped by an ellipsis: a catch
  can't check  the typed file is missing, unreadable, not UTF-8 or empty; no
               quote was found; a page is unreadable; a quote holds a backtick
A quote is the text between *" and "* on one line, outside code; … marks words
left out. A quote followed by (spoken) is counted, never checked.

What it compares against: the typed-messages file (default WORDS.txt in the
repository root; --words to name another), a plain UTF-8 file of messages
separated by blank lines. What it reads: every top-level .md file of the
repository, or the files named.

What it cannot see: meaning (a one-letter change such as strong to wrong, or
learning to earning, reads corrected; a verbatim fragment cut from a negated
sentence reads exact; an … over three or more plain words reads exact: read
the change and the words shown around it); a quote not marked with *" "*; a
quote split over two lines; anything typed that is not in the typed file; a
negation outside its closed list (not, no, never, none, nor, cannot, nothing,
nobody, nowhere, neither, any word ending in n't, and dont, cant, wont and the
other apostrophe-less forms in the code): a word such as without is not on it,
so dropping one reads corrected. A replacement that keeps the negation (dont to
don't) is a typing fix and reads corrected; a flipped or dropped negation is
absent.

Exit: 0 nothing absent or unchecked · 1 a quote is absent · 2 none absent,
some could not be checked. The exit is a report; nothing stops on it. Anything
unhandled is one line under could not see, exit 2, never a traceback."""


# ---------------------------------------------------------------- words

def fold(token):
    return token.translate(CURLY).lower().strip(EDGE)


def is_negation(word):
    w = fold(word)
    return w in NEGATIONS or w.endswith("n't") or w in BARE_NT


def same_negation(a, b):
    """dont and don't are one word typed two ways, not a flipped negation."""
    return fold(a).replace("'", "") == fold(b).replace("'", "")


def edits(a, b):
    """Damerau-Levenshtein distance (unrestricted transpositions)."""
    inf = len(a) + len(b)
    last = {}
    d = [[inf] * (len(b) + 2) for _ in range(len(a) + 2)]
    for i in range(len(a) + 1):
        d[i + 1][0], d[i + 1][1] = inf, i
    for j in range(len(b) + 1):
        d[0][j + 1], d[1][j + 1] = inf, j
    for i in range(1, len(a) + 1):
        db = 0
        for j in range(1, len(b) + 1):
            i1, j1 = last.get(b[j - 1], 0), db
            cost = 0 if a[i - 1] == b[j - 1] else 1
            if cost == 0:
                db = j
            d[i + 1][j + 1] = min(d[i][j] + cost, d[i + 1][j] + 1, d[i][j + 1] + 1,
                                  d[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1))
        last[a[i - 1]] = i
    return d[len(a) + 1][len(b) + 1]


class Tok:
    __slots__ = ("raw", "f", "start", "end")

    def __init__(self, m):
        self.raw, self.start, self.end = m.group(), m.start(), m.end()
        self.f = fold(self.raw)


def tokens(text):
    """Words after folding: runs of non-space characters, empties dropped."""
    return [t for t in (Tok(m) for m in re.finditer(r"\S+", text)) if t.f]


def describe_space(s):
    if s == " ":
        return "one space"
    if set(s) == {" "}:
        return f"{len(s)} spaces"
    return "a line break" if "\n" in s else ("a tab" if "\t" in s else repr(s))


# ---------------------------------------------------------------- inputs

def read_messages(path):
    """(messages, problem): each message the text of one block of non-blank lines."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        return [], "missing"
    except OSError as exc:
        return [], f"unreadable ({type(exc).__name__})"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [], "not UTF-8"
    blocks = split_blocks(text.removeprefix("﻿"))
    return blocks, (None if blocks else "holds no message")


def is_blank(line):
    """The one rule for a blank line, shared by both halves: strip() empties it
    (a carriage return, a tab or a no-break space alone is blank)."""
    return line.strip() == ""


def split_blocks(text):
    """The typed file's messages: blocks of non-blank lines, a trailing carriage
    return taken off each line. The extractor's --times counts blocks with this."""
    blocks, block = [], []
    for line in text.split("\n"):
        line = line.removesuffix("\r")
        if is_blank(line):
            if block:
                blocks.append("\n".join(block))
            block = []
        else:
            block.append(line)
    if block:
        blocks.append("\n".join(block))
    return blocks


def _skip_code(line, i):
    """At a backtick run: the index after its code span, or after the run alone."""
    run = len(line) - len(line[i:].lstrip("`"))
    ticks = "`" * run
    j = i + run
    while True:
        k = line.find(ticks, j)
        if k < 0:
            return i + run, False
        if line[k + run:k + run + 1] != "`" and (k == 0 or line[k - 1] != "`"):
            return k + run, True
        j = k + 1


def find_quotes(text):
    """[(line, raw, has_backtick, spoken)] outside fenced blocks and code spans."""
    found, fence = [], None
    for n, line in enumerate(text.split("\n"), 1):
        line = line.removesuffix("\r")
        m = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and line.strip() == m.group(1):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        i = 0
        while i < len(line):
            if line[i] == "`":
                i, _ = _skip_code(line, i)
                continue
            if line.startswith(OPEN, i):
                j, tick = i + 2, False
                while j < len(line) and not line.startswith(CLOSE, j):
                    if line[j] == "`":
                        tick = True
                        j, _ = _skip_code(line, j)
                    else:
                        j += 1
                if j < len(line):
                    spoken = re.match(r"[ \t]*\(spoken\)", line[j + 2:]) is not None
                    found.append((n, line[i + 2:j], tick, spoken))
                    i = j + 2
                    continue
                i += 2
                continue
            i += 1
    return found


def split_parts(raw):
    pieces = raw.split(ELLIPSIS)
    parts = [p.strip() for p in pieces if p.strip()]
    lead = len(pieces) > 1 and not pieces[0].strip()
    trail = len(pieces) > 1 and not pieces[-1].strip()
    return parts, lead, trail


# ---------------------------------------------------------------- matching

def _bounded(text, k, part):
    if part[0].isalnum() and k > 0 and text[k - 1].isalnum():
        return False
    e = k + len(part)
    return not (part[-1].isalnum() and e < len(text) and text[e].isalnum())


def _gap_ok_exact(text, a, b):
    words = tokens(text[a:b])
    return len(words) >= 3 and not any(is_negation(w.raw) for w in words)


def exact_place(text, parts, lead, trail):
    """Char spans for each part, character for character, every … over three or
    more typed words with no negation among them; None when there is none."""
    def go(idx, pos, spans):
        if idx == len(parts):
            if trail and not _gap_ok_exact(text, spans[-1][1], len(text)):
                return None
            return spans
        part, k = parts[idx], text.find(parts[idx], pos)
        while k >= 0:
            if _bounded(text, k, part):
                gap_ok = True
                if idx == 0 and lead:
                    gap_ok = _gap_ok_exact(text, 0, k)
                elif idx > 0:
                    gap_ok = _gap_ok_exact(text, pos, k)
                if gap_ok:
                    got = go(idx + 1, k + len(part), spans + [(k, k + len(part))])
                    if got:
                        return got
            k = text.find(part, k + 1)
        return None
    return go(0, 0, [])


def _replace_cost(q, m):
    """0 equal, 1 a typo within two letter edits, None not allowed."""
    if q.f == m.f:
        return 0
    if (is_negation(q.raw) or is_negation(m.raw)) and not same_negation(q.raw, m.raw):
        return None
    return 1 if edits(q.f, m.f) <= 2 else None


def part_spans(qt, mt):
    """Every alignment of one part's words to a span of the message: no word
    added, at most two typed words dropped, each replacement a typo."""
    out = []
    for s in range(len(mt)):
        c0 = _replace_cost(qt[0], mt[s])
        if c0 is None:
            continue
        states = [(1, s + 1, 0, c0, [("a", 0, s)])]
        while states:
            nxt = []
            for i, j, d, cost, ops in states:
                if i == len(qt):
                    out.append((s, j, cost, d, ops))
                    continue
                for k in range(0, 3 - d):
                    if j + k >= len(mt):
                        break
                    dropped = mt[j:j + k]
                    if any(is_negation(t.raw) for t in dropped):
                        break
                    c = _replace_cost(qt[i], mt[j + k])
                    if c is None:
                        continue
                    nxt.append((i + 1, j + k + 1, d + k, cost + k + c,
                                ops + [("d", None, j + x) for x in range(k)] +
                                [("a", i, j + k)]))
            states = nxt
    return out


def corrected_place(text, parts, lead, trail, neg=True, ordered=True):
    """The place where a quote reads corrected, or None. The two switches never
    decide an outcome: diagnose turns one rule off at a time to learn which rule
    alone kept an absent quote from reading corrected."""
    mt = tokens(text)
    qts = [tokens(p) for p in parts]
    if any(not q for q in qts):
        return None
    budget = math.ceil(sum(len(q) for q in qts) / 8)
    cands = [sorted((c for c in part_spans(q, mt) if c[2] <= budget),
                    key=lambda c: (c[2], c[0])) for q in qts]
    best = None

    def neg_in(a, b):
        return any(is_negation(t.raw) for t in mt[a:b])

    def go(idx, pos, cost, drops, chosen):
        nonlocal best
        if best and cost > best[0]:
            return
        if idx == len(parts):
            if neg and trail and neg_in(chosen[-1][1], len(mt)):
                return
            if not ordered and [c[0] for c in chosen] == sorted(c[0] for c in chosen):
                return
            key = (cost, [c[0] for c in chosen])
            if best is None or key < (best[0], [c[0] for c in best[1]]):
                best = (cost, list(chosen))
            return
        for c in cands[idx]:
            s, e, ccost, cd, _ = c
            if cost + ccost > budget or drops + cd > 2:
                continue
            if ordered:
                if s < pos:
                    continue
                if neg and idx == 0 and lead and neg_in(0, s):
                    continue
                if neg and idx > 0 and neg_in(pos, s):
                    continue
            elif any(s < pe and ps < e for ps, pe, *_ in chosen):
                continue
            go(idx + 1, e, cost + ccost, drops + cd, chosen + [c])
    go(0, 0, 0, 0, [])
    if best is None:
        return None
    return mt, qts, best[1]


def name_differences(text, parts, lead, trail, mt, qts, chosen):
    diffs = []
    for p, q, (s, e, _, _, ops) in zip(parts, qts, chosen):
        prev = None
        for op, qi, mj in ops:
            m = mt[mj]
            if op == "d":
                diffs.append(f"{m.raw} → [dropped] (drop)")
                prev = None
                continue
            t = q[qi]
            if prev is not None:
                ms, qs = text[mt[prev[1]].end:m.start], p[q[prev[0]].end:t.start]
                if ms != qs:
                    if not ms.strip() and not qs.strip():
                        diffs.append(f"after \"{q[prev[0]].raw}\": {describe_space(ms)}"
                                     f" → {describe_space(qs)} (spacing)")
                    else:
                        diffs.append(f"\"{ms}\" → \"{qs}\" (punctuation)")
            if t.f != m.f:
                diffs.append(f"{m.raw} → {t.raw} (edit)")
            elif t.raw != m.raw:
                cm, cq = m.raw.translate(CURLY).strip(EDGE), t.raw.translate(CURLY).strip(EDGE)
                kinds = []
                if cm != cq:
                    kinds.append("case")
                if (m.raw.translate(CURLY).lower().replace(cm.lower(), "", 1) !=
                        t.raw.translate(CURLY).lower().replace(cq.lower(), "", 1)
                        or m.raw.translate(CURLY) != m.raw or t.raw.translate(CURLY) != t.raw):
                    kinds.append("punctuation")
                diffs.append(f"{m.raw} → {t.raw} ({', '.join(kinds) or 'punctuation'})")
            prev = (qi, mj)
    gaps = []
    if lead:
        gaps.append((0, chosen[0][0]))
    gaps += [(chosen[i][1], chosen[i + 1][0]) for i in range(len(chosen) - 1)]
    if trail:
        gaps.append((chosen[-1][1], len(mt)))
    for a, b in gaps:
        if b - a == 0:
            diffs.append("… marks nothing (gap)")
        elif b - a < 3:
            diffs.append(f"… skipped \"{' '.join(t.raw for t in mt[a:b])}\" (gap)")
    return diffs


def context(text, start, end):
    words = [m for m in re.finditer(r"\S+", text)]
    before = [m.group() for m in words if m.end() <= start][-3:]
    after = [m.group() for m in words if m.start() >= end][:3]
    return (" ".join(before) or "[start]"), (" ".join(after) or "[end]")


def _splice_reason(messages, parts, lead, trail):
    """Which single rule kept an absent quote from reading corrected, learned by
    turning that one rule off in the same search that decides the outcome, so a
    reason is given only when it is the cause. First, in any message: with the
    negation rule off the quote places, so an … covers a negation (where, as a
    count of typed words, never the word). Else: with the order rule off it
    places, in an order that is not the quote's. Else None."""
    for n, text in enumerate(messages, 1):
        got = corrected_place(text, parts, lead, trail, neg=False)
        if not got:
            continue
        mt, _, chosen = got
        spots = [(chosen[i][1], chosen[i + 1][0], i) for i in range(len(chosen) - 1)]
        for a, b, i in spots:
            if any(is_negation(t.raw) for t in mt[a:b]):
                return n, f"an … skips a negation, between parts {i + 1} and {i + 2}"
        if trail:
            a = chosen[-1][1]
            k = next((j - a + 1 for j in range(a, len(mt)) if is_negation(mt[j].raw)), None)
            if k:
                return n, f"an … skips a negation, {k} typed words past the quote's end"
        if lead:
            a = chosen[0][0]
            k = next((a - j for j in range(a - 1, -1, -1) if is_negation(mt[j].raw)), None)
            if k:
                return n, f"an … skips a negation, {k} typed words before the quote's start"
    if len(parts) > 1:
        for n, text in enumerate(messages, 1):
            if corrected_place(text, parts, lead, trail, neg=False, ordered=False):
                return n, "the parts are out of order"
    return None


def diagnose(messages, parts, lead=False, trail=False):
    """Why a quote is absent: the nearest message and the first rule it breaks."""
    qt = [t for p in parts for t in tokens(p)]
    best = None
    for n, text in enumerate(messages, 1):
        mt = tokens(text)
        if not mt or not qt:
            continue
        # cheapest local alignment: replace, add (quote word not typed), drop
        inf = 10 ** 6
        cost = [[inf] * (len(mt) + 1) for _ in range(len(qt) + 1)]
        back = [[None] * (len(mt) + 1) for _ in range(len(qt) + 1)]
        for j in range(len(mt) + 1):
            cost[0][j] = 0
        for i in range(1, len(qt) + 1):
            cost[i][0], back[i][0] = 3 * i, ("add", i - 1, None)
            for j in range(1, len(mt) + 1):
                q, m = qt[i - 1], mt[j - 1]
                sub = 0 if q.f == m.f else (1 if edits(q.f, m.f) <= 2 else 2)
                opts = [(cost[i - 1][j - 1] + sub, ("sub", i - 1, j - 1)),
                        (cost[i - 1][j] + 3, ("add", i - 1, None)),
                        (cost[i][j - 1] + 1, ("drop", None, j - 1))]
                cost[i][j], back[i][j] = min(opts, key=lambda o: o[0])
        j = min(range(len(mt) + 1), key=lambda j: cost[len(qt)][j])
        total = cost[len(qt)][j]
        if best is None or total < best[0]:
            ops, i = [], len(qt)
            while i > 0:
                op = back[i][j]
                ops.append(op)
                if op[0] == "sub":
                    i, j = i - 1, j - 1
                elif op[0] == "add":
                    i -= 1
                else:
                    j -= 1
            best = (total, n, list(reversed(ops)), mt)
    if best is None or len([o for o in best[2] if o[0] == "sub"]) == 0:
        return None, "no message holds its words"
    _, n, ops, mt = best
    same = sum(1 for o, i, j in ops if o == "sub" and qt[i].f == mt[j].f)
    if same == 0:
        return None, "no message holds its words"
    found = _splice_reason(messages, parts, lead, trail)  # the cause, when one rule alone is it
    if found:
        return found
    for o, i, j in ops:
        if o == "sub" and qt[i].f != mt[j].f and (is_negation(qt[i].raw) or
                                                  is_negation(mt[j].raw)):
            return n, f"a negation changed: {mt[j].raw} → {qt[i].raw}"
        if o == "drop" and is_negation(mt[j].raw):
            return n, f"a negation dropped or skipped: {mt[j].raw}"
        if o == "add" and is_negation(qt[i].raw):
            return n, f"a negation added: {qt[i].raw}"
    adds = [qt[i].raw for o, i, j in ops if o == "add"]
    if adds:
        return n, f"the quote adds a word the message lacks: {', '.join(adds)}"
    far = [(mt[j].raw, qt[i].raw) for o, i, j in ops
           if o == "sub" and qt[i].f != mt[j].f and edits(qt[i].f, mt[j].f) > 2]
    if far:
        return n, f"more than two letter edits: {far[0][0]} → {far[0][1]}"
    differ = sum(1 for o, i, j in ops if o == "drop" or (o == "sub" and qt[i].f != mt[j].f))
    drops = sum(1 for o, _, _ in ops if o == "drop")
    if drops > 2:
        return n, f"{drops} typed words dropped; at most two"
    allowed = math.ceil(len(qt) / 8)
    if differ > allowed:
        return n, f"{differ} of {len(qt)} words differ; at most {allowed}"
    return n, "an … skips a negation, or the parts are out of order (which, it cannot tell)"


# ---------------------------------------------------------------- the run

def _rel(path, root):
    real = os.path.realpath(path)
    if runlog.repo_root(real) == root:
        return os.path.relpath(real, root).replace(os.sep, "/")
    return None


def check(sources, words):
    """Return (lines, counts, read, compared_against, could_not, caught)."""
    root = runlog.module_root()
    counts = dict.fromkeys(["exact", "corrected", "absent", "cant_check", "spoken"], 0)
    lines, could_not, caught, read = [], [], [], []
    words_rel = _rel(words, root)
    words_name = words_rel or "outside the repository (the typed-messages file)"
    compared = [words_rel or runlog.OUTSIDE]
    messages, problem = read_messages(words)
    if problem:
        could_not.append(f"{words_name}: {problem}")
    any_quote = False
    for number, src in enumerate(sources, 1):
        rel = _rel(src, root)
        name = rel or f"outside the repository (file {number})"
        if rel and rel not in read:
            read.append(rel)
        elif not rel and runlog.OUTSIDE not in read:
            read.append(runlog.OUTSIDE)
        private = rel is None or words_rel is None
        try:
            with open(src, "rb") as fh:
                text = fh.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            why = "not UTF-8" if isinstance(exc, UnicodeDecodeError) else \
                f"unreadable ({type(exc).__name__})"
            counts["cant_check"] += 1
            lines.append(f"CAN'T CHECK · {name} · {why}")
            could_not.append(f"{name}: {why}")
            continue
        for line_no, raw, tick, spoken in find_quotes(text):
            any_quote = True
            where = f"{name}:{line_no}"
            shown = raw.split()
            first = "" if rel is None else \
                " · " + " ".join(shown[:6]) + ("…" if len(shown) > 6 else "")
            if spoken:
                counts["spoken"] += 1
                lines.append(f"SPOKEN · {where}{first} · marked spoken: counted, not checked")
                continue
            parts, lead, trail = split_parts(raw)
            why = None
            if tick:
                why = "the quote holds a backtick (quotes hold prose, never code)"
            elif not parts:
                why = "the quote holds no words"
            elif problem:
                why = f"{words_name}: {problem}"
            if why:
                counts["cant_check"] += 1
                lines.append(f"CAN'T CHECK · {where}{first} · {why}")
                if not problem:  # the typed file's own line already says why
                    could_not.append(f"{where}: {why}")
                continue
            exact = [(n, exact_place(t, parts, lead, trail)) for n, t in enumerate(messages, 1)]
            exact = [(n, s) for n, s in exact if s]
            corr = [(n, corrected_place(t, parts, lead, trail))
                    for n, t in enumerate(messages, 1)]
            corr = [(n, c) for n, c in corr if c]
            if exact or corr:
                n = (exact or corr)[0][0]
                text_m = messages[n - 1]
                # every message that holds it, exact or corrected, is counted
                matched = len({m for m, _ in exact} | {m for m, _ in corr})
                many = f" ({matched} matched)" if matched > 1 else ""
                if exact:
                    spans = exact[0][1]
                    start, end, outcome, diffs = spans[0][0], spans[-1][1], "exact", []
                else:
                    mt, qts, chosen = corr[0][1]
                    start, end = mt[chosen[0][0]].start, mt[chosen[-1][1] - 1].end
                    outcome = "corrected"
                    diffs = name_differences(text_m, parts, lead, trail, mt, qts, chosen)
                counts[outcome] += 1
                if private:
                    detail = f"{len(diffs)} difference(s) named" if diffs else "as typed"
                    lines.append(f"{outcome.upper()} · {where} · message {n}{many} · {detail}")
                else:
                    before, after = context(text_m, start, end)
                    detail = "; ".join(diffs) if diffs else "as typed"
                    lines.append(f"{outcome.upper()} · {where}{first} · message {n}{many}"
                                 f" · {detail} · before: {before} · after: {after}")
                continue
            counts["absent"] += 1
            near, why = diagnose(messages, parts, lead, trail)
            nearest = f" · nearest: message {near}" if near else ""
            if private:
                why = why.split(":")[0]
            lines.append(f"ABSENT · {where}{first}{nearest} · {why}")
            caught.append(f"absent · {where}{first} · {why}")
    if not any_quote:
        counts["cant_check"] += 1
        lines.append("CAN'T CHECK · no quote was found in the source files")
        could_not.append("no quote was found in the source files")
    return lines, counts, read, compared, could_not, caught


def exit_code(counts):
    return 1 if counts["absent"] else (2 if counts["cant_check"] else 0)


def summary(counts, read, compared, could_not):
    out = [f"exact: {counts['exact']} · corrected: {counts['corrected']} · absent: "
           f"{counts['absent']} · can't check: {counts['cant_check']} · spoken: {counts['spoken']}"]
    out.append("read: " + (", ".join(read) or "nothing"))
    out.append("compared against: " + ", ".join(compared))
    out.append("could not see: " + ("; ".join(could_not) if could_not else
                                    "nothing missing in what it was given (meaning is never seen)"))
    return out


def log(kind, note, invoked, read, compared, counts, caught, could_not):
    path = runlog.write(TOOL, OWN_FILES, kind, note, invoked, read, compared,
                        row_outcomes(counts), caught, could_not)
    print(f"logged: {shown_path(path)} ({kind})")


def row_outcomes(counts):
    return {k: counts[k] for k in ("exact", "corrected", "absent", "cant_check", "spoken")}


def shown_path(path):
    root = runlog.module_root()
    return os.path.relpath(path, root) if path.startswith(root) else path


# ---------------------------------------------------------------- self-test

TESTS = os.path.join(HERE, "tests")


def selftest(no_log):
    results, totals, absent_cases = [], dict.fromkeys(
        ["exact", "corrected", "absent", "cant_check", "spoken"], 0), []
    cases = sorted(d for d in os.listdir(TESTS)
                   if os.path.isfile(os.path.join(TESTS, d, "expect.toml")))
    for case in cases:
        folder = os.path.join(TESTS, case)
        with open(os.path.join(folder, "expect.toml"), "rb") as fh:
            want = tomllib.load(fh)
        pages = sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".md"))
        words = os.path.join(folder, want.get("words", "words.txt"))
        if want.get("mode") in ("real-run", "unwritable-log", "bad-note"):
            # a person's run, logging on, over fixture pages. real-run: the run log
            # refuses a real row that read fixtures. unwritable-log: the log folder
            # (a scratch folder, never runs/) cannot be written. Either reads can't
            # check, one line, no crash; exit 1 only when a quote is absent.
            import contextlib
            import io
            import tempfile
            buf = io.StringIO()
            with tempfile.TemporaryDirectory() as tmp:
                locked = os.path.join(tmp, "runs")
                os.makedirs(locked)
                saved = runlog.default_folder
                if want["mode"] in ("unwritable-log", "bad-note"):
                    runlog.default_folder = lambda files=None: locked
                if want["mode"] == "unwritable-log":
                    os.chmod(locked, 0o555)
                try:
                    if want["mode"] == "unwritable-log" and os.access(locked, os.W_OK):
                        print(f"skip {case}: a locked folder is writable here")
                        os.chmod(locked, 0o755)
                        continue
                    extra = {"unwritable-log": ["--planted", "selftest"],
                             "bad-note": ["--planted", "a note \udcff"]}.get(want["mode"], [])
                    with contextlib.redirect_stdout(buf):
                        code = main(pages + ["--words", words] + extra)
                    rows = os.listdir(locked)
                finally:
                    runlog.default_folder = saved
                    os.chmod(locked, 0o755)
            if rows:
                code = "a row was written"
            lines = buf.getvalue().splitlines()
            ok = code == want["exit"] and all(any(n in line for line in lines)
                                              for n in want.get("contains", []))
            results.append(ok)
            print(f"{'ok  ' if ok else 'FAIL'} {case}: a real run, exit {code}")
            for line in lines:
                print(f"       {line}")
            continue
        lines, counts, _, _, _, _ = check(pages, words)
        got = {k: v for k, v in counts.items() if v}
        code = exit_code(counts)
        ok = got == want["outcomes"] and code == want["exit"]
        for needle in want.get("contains", []):
            ok = ok and any(needle in line for line in lines)
        results.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {case}: {got} exit {code}")
        for line in lines:
            print(f"       {line}")
        for k, v in counts.items():
            totals[k] += v
        if counts["absent"]:
            absent_cases.append(f"fixture {case}: {counts['absent']} absent")
    passed = bool(results) and all(results)
    print(f"{sum(results)}/{len(results)} fixtures")
    if not no_log:
        log("planted", "selftest", "selftest", ["fixture"], ["fixture"], totals,
            absent_cases, [])
    print("selftest: PASS" if passed else "selftest: FAIL")
    return 0 if passed else 1


def main(argv):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass  # a replaced stdout (the self-test's) keeps its own rule
    try:
        return _main(argv)
    except Exception as exc:  # the net: never a traceback, never 1, no row
        print(f"could not see: {type(exc).__name__}")
        return 2


def _main(argv):
    ap = argparse.ArgumentParser(prog="your_words.py", description=HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="*", help="markdown files (default: every top-level .md)")
    ap.add_argument("--words", help="the typed-messages file (default: WORDS.txt)")
    ap.add_argument("--planted", metavar="NOTE", help="log a planted row: what, by whom")
    ap.add_argument("--no-log", action="store_true", help="write no row (the workflow)")
    ap.add_argument("--selftest", action="store_true", help="run the committed fixtures")
    ap.add_argument("--files", action="store_true", help="print the tool's own files")
    ap.add_argument("--earned-by", action="store_true", help="print the founding failure")
    ap.add_argument("--catching", action="store_true", help="print the four outcome names")
    args = ap.parse_args(argv)
    if args.files:
        print("\n".join(OWN_FILES))
        return 0
    if args.earned_by:
        print(EARNED_BY)
        return 0
    if args.catching:
        print("\n".join(CATCHING))
        return 0
    if args.selftest:
        try:
            return selftest(args.no_log)
        except Exception as exc:  # a crash is a failure, never a silent end
            print(f"FAIL self-test crashed: {type(exc).__name__}: {exc}")
            print("selftest: FAIL")
            return 1
    if args.planted is not None and not args.planted.strip():
        print("can't check: --planted needs a note saying what was planted and by whom")
        return 2
    root = runlog.module_root()
    sources = args.sources or sorted(
        os.path.join(root, f) for f in os.listdir(root) if f.endswith(".md"))
    words = args.words or os.path.join(root, "WORDS.txt")
    lines, counts, read, compared, could_not, caught = check(sources, words)
    for line in lines:
        print(line)
    refused, path, kind = None, None, "planted" if args.planted else "real"
    if not args.no_log:
        try:
            path = runlog.write(TOOL, OWN_FILES, kind, args.planted or "", "person", read,
                                compared, row_outcomes(counts), caught, could_not)
        except (runlog.RunLogError, OSError) as exc:
            detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
            refused = (f"the run log refused this run's row ({type(exc).__name__}: {detail});"
                       " nothing was logged" + ("; a run on fixtures is a plant: give"
                                                " --planted" if kind == "real" and
                                                isinstance(exc, runlog.RunLogError) else ""))
            counts["cant_check"] += 1
            print(f"CAN'T CHECK · {refused}")
            could_not.append(refused)
    for line in summary(counts, read, compared, could_not):
        print(line)
    if refused:
        # never a crash: an absent quote still exits 1 (the spec's rule, even
        # when others could not be checked), else the refusal is a can't tell, 2
        return exit_code(counts)
    if path:
        print(f"logged: {shown_path(path)} ({kind})")
    return exit_code(counts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
