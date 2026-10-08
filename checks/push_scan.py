#!/usr/bin/env python3
"""Check 5 · the push scanner: keeps the words on a list out of a repository.

What it compares: path names, file contents, commit objects (author, committer, message) and
tag objects against a word list (default: the invented sample, checks/push-scan.sample.txt).
How it is fired: as check 5 by checks/run_all.py (--tree), on every push and pull request by
the workflow; as a pre-push hook (checks/hook-pre-push.sample, --prepush); by hand
(--files, --stdin, --history). The failure that earned it: the first private version was proven
only on words planted where its author expected them, and a separate review found five ways a
word could slip past (another case, full-width letters, an invisible character inside, a UTF-16
file, a stray NUL that made git call a text file binary).
Its twin: --tree that decodes zero files as text is RED, never green (blind to the repository).
What it does not prove, and does not see: that a list is complete; a word split across lines or
spelled with spaces; a word inside a compressed, encrypted or binary file, inside a submodule
(counted by name, not scanned) or behind a symbolic link (its target's path text is scanned, the
link never followed); an unmarked UTF-16 file without a text extension; a disguise outside the
foldings below and outside its small, hand-kept look-alike table.

  push_scan.py --tree              this repository: tracked path names and working files, and
                                   the current commit's raw object; prints the guard's one line
  push_scan.py --files F [F ...]   the given files, as given (no exclusions)
  push_scan.py --stdin             text on standard input (a commit message, say)
  push_scan.py --history REPO      every commit reachable from any ref, every path and file in
                                   each, every tag object
  push_scan.py --prepush           git's pre-push lines on standard input, "<local ref> <local id>
                                   <remote ref> <remote id>"; scans what the remote lacks
  push_scan.py --list PATH         another word list (one that stays private, say)
  push_scan.py --selftest          15 plants, 2 controls, foldings, twin, unreadable, the hook

Matching: before matching, text is folded in this order: Unicode NFKC (full-width forms,
superscripts), invisible format characters removed (zero-width spaces and joiners, soft
hyphens), the look-alike table (Cyrillic a c e o p x y to Latin; digits 0 1 3 5 to o l e s), then
lower case. A list line is a word or phrase; "w:" matches only with a non-word character or the
text's edge on both sides (a word character is a letter or digit after folding); "#" lines are
comments; an empty list is CAN'T TELL.
Read as text: a file with a text extension is decoded as UTF-8, and also as UTF-16 in both byte
orders when it carries a mark or NUL bytes, every successful reading scanned; one that decodes
no way is CAN'T TELL. Any other file: UTF-16 when it carries a mark, else UTF-8 with replacement
when its first 8,000 bytes hold no NUL (git's own rule), else counted by name as binary.
Exclusions (--tree, --history, --prepush): exactly the paths named in
checks/tests/push_scan/MANIFEST, name and content; in --history and --prepush each commit is
read against the MANIFEST as it was in that commit. An entry naming anything but the sample list
or a file under checks/tests/push_scan/ is RED: a manifest that may name anything is a hiding place.
Exit 0 nothing hit · 1 a hit (even beside something unreadable), or the twin · 2 could not look.
As a hook, 1 and 2 both refuse the push. In run_all it reports, like every other check.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "push-scan.sample.txt")
SAMPLE_REL = "checks/push-scan.sample.txt"
MANIFEST_REL = "checks/tests/push_scan/MANIFEST"
FIXTURE_DIR_REL = "checks/tests/push_scan/"
ZERO = "0" * 40
TEXT_EXT = {".md", ".txt", ".toml", ".py", ".yml", ".yaml", ".json", ".html", ".sample"}
MARKS = (b"\xff\xfe", b"\xfe\xff")
LOOKALIKE = str.maketrans({
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x",
    "у": "y", "А": "a", "С": "c", "Е": "e", "О": "o", "Р": "p",
    "Х": "x", "У": "y", "0": "o", "1": "l", "3": "e", "5": "s",
})


class CannotLook(Exception):
    pass


def fold(text):
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.translate(LOOKALIKE).lower()


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except (OSError, UnicodeDecodeError) as e:
        raise CannotLook(f"word list unreadable: {path}: {e.__class__.__name__}")
    terms = []
    for raw in lines:
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        whole = entry.startswith("w:")
        body = fold(entry[2:] if whole else entry)
        if not body:
            continue
        pat = re.escape(body)
        if whole:
            pat = r"(?<![^\W_])" + pat + r"(?![^\W_])"
        terms.append((entry, re.compile(pat)))
    if not terms:
        raise CannotLook(f"the word list has no entries: {path}")
    return terms


def readings(name, data):
    """Return (texts, kind): kind is 'text', 'binary' or 'undecodable'."""
    ext = os.path.splitext(name)[1].lower()
    marked = data[:2] in MARKS
    if ext in TEXT_EXT:
        texts = []
        try:
            texts.append(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            pass
        if marked or b"\x00" in data:
            body = data[2:] if marked else data
            for enc in ("utf-16-le", "utf-16-be"):
                try:
                    texts.append(body.decode(enc))
                except UnicodeDecodeError:
                    pass
        return (texts, "text") if texts else ([], "undecodable")
    if marked:
        try:
            return [data.decode("utf-16")], "text"
        except UnicodeDecodeError:
            return [], "undecodable"
    if b"\x00" not in data[:8000]:
        return [data.decode("utf-8", errors="replace")], "text"
    return [], "binary"


class Scan:
    """Collects hits, counts and what could not be read, for one run."""

    def __init__(self, terms):
        self.terms = terms
        self.hits = []
        self.seen = set()
        self.cant = []
        self.text = self.binary = self.submodules = 0
        self.skipped = set()

    def hit(self, where, line, label):
        key = (where, line, label)
        if key not in self.seen:
            self.seen.add(key)
            self.hits.append(key)

    def scan_text(self, text, where):
        for n, line in enumerate(text.split("\n"), 1):
            folded = fold(line)
            for entry, rx in self.terms:
                if rx.search(folded):
                    self.hit(where, n, entry)

    def scan_name(self, path):
        folded = fold(path)
        for entry, rx in self.terms:
            if rx.search(folded):
                self.hit(f"{path} name", 0, entry)

    def scan_bytes(self, name, data, where):
        texts, kind = readings(name, data)
        if kind == "binary":
            self.binary += 1
        elif kind == "undecodable":
            self.cant.append(f"{where} decodes no way")
        else:
            self.text += 1
            for t in texts:
                self.scan_text(t, where)


def git(args, cwd, data=None):
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off"] + args, cwd=cwd, input=data,
                           capture_output=True)
    except OSError as e:
        raise CannotLook(f"git could not run: {e}")
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise CannotLook(f"git {args[0]} exited {p.returncode}: {err[-1] if err else 'no message'}")
    return p.stdout


class Store:
    """Reads git objects through one `git cat-file --batch` process."""

    def __init__(self, repo):
        self.p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read(self, oid):
        self.p.stdin.write(oid.encode() + b"\n")
        self.p.stdin.flush()
        head = self.p.stdout.readline()
        parts = head.split()
        if len(parts) != 3:
            raise CannotLook(f"object {oid[:12]} missing or unreadable")
        data = self.p.stdout.read(int(parts[2]))
        self.p.stdout.read(1)
        return parts[1].decode(), data

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=30)
        except Exception:
            self.p.kill()
        if self.p.returncode not in (0, None, -9):
            raise CannotLook(f"git cat-file exited {self.p.returncode}")


def parse_manifest(text, scan, where):
    excluded = set()
    for n, raw in enumerate(text.split("\n"), 1):
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry == SAMPLE_REL or (entry.startswith(FIXTURE_DIR_REL) and ".." not in entry):
            excluded.add(entry)
        else:
            scan.hit(where, n, "entry outside the sample list and the fixtures folder")
    return excluded


def tree_entries(repo, commit):
    out = git(["ls-tree", "-r", "-z", "--full-tree", commit], repo)
    entries = []
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, oid = meta.decode().split()
        entries.append((mode, typ, oid, path.decode("utf-8", "replace")))
    return entries


def scan_commit(repo, store, oid, scan, state):
    typ, raw = store.read(oid)
    scan.scan_text(raw.decode("utf-8", "replace"), f"commit {oid[:12]}")
    entries = tree_entries(repo, oid)
    excluded = set()
    for mode, t, boid, path in entries:
        if path == MANIFEST_REL and t == "blob":
            excluded = parse_manifest(store.read(boid)[1].decode("utf-8", "replace"), scan,
                                      f"{oid[:12]}:{MANIFEST_REL}")
    for mode, t, boid, path in entries:
        if path in excluded:
            scan.skipped.add(path)
            continue
        if path not in state["paths"]:
            state["paths"].add(path)
            scan.scan_name(path)
        if t == "commit":
            scan.submodules += 1
            continue
        if boid in state["blobs"]:
            continue
        state["blobs"].add(boid)
        scan.scan_bytes(path, store.read(boid)[1], f"{oid[:12]}:{path}")


def skipped_text(scan):
    if not scan.skipped:
        return "skipped nothing"
    return f"skipped {len(scan.skipped)} named by {MANIFEST_REL}: " + ", ".join(sorted(scan.skipped))


def mode_tree(list_path, list_name):
    """Check 5's mode: one line, the guard's format."""
    scan = None
    try:
        terms = load_list(list_path)
        scan = Scan(terms)
        root = git(["rev-parse", "--show-toplevel"], os.getcwd()).decode().strip()
        excluded = set()
        man = os.path.join(root, MANIFEST_REL)
        if os.path.isfile(man):
            with open(man, encoding="utf-8", errors="replace") as f:
                excluded = parse_manifest(f.read(), scan, MANIFEST_REL)
        commits = 0
        has_head = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=root,
                                  capture_output=True).returncode == 0
        if has_head:
            raw = git(["cat-file", "commit", "HEAD"], root)
            scan.scan_text(raw.decode("utf-8", "replace"), "commit HEAD")
            commits = 1
        out = git(["ls-files", "-s", "-z"], root)
        for rec in out.split(b"\0"):
            if not rec:
                continue
            meta, path = rec.split(b"\t", 1)
            mode, oid, _stage = meta.decode().split()
            path = path.decode("utf-8", "replace")
            if path in excluded:
                scan.skipped.add(path)
                continue
            scan.scan_name(path)
            full = os.path.join(root, path)
            if mode == "160000":
                scan.submodules += 1
                continue
            if os.path.islink(full):
                data = os.readlink(full).encode("utf-8", "replace")
            elif os.path.isfile(full):
                with open(full, "rb") as f:
                    data = f.read()
            else:
                data = git(["cat-file", "blob", oid], root)
            scan.scan_bytes(path, data, path)
    except CannotLook as e:
        if scan and scan.hits:
            w, n, t = scan.hits[0]
            print(f"RED: {len(scan.hits)} hit(s), first {w}:{n}: [{t}]; then could not look: {e}")
            return 1
        print(f"CAN'T TELL: {e}")
        return 2
    read = (f"read {scan.text} files, {scan.binary} binary counted, {commits} commit"
            + (f", {scan.submodules} submodules counted" if scan.submodules else ""))
    if scan.hits:
        w, n, t = scan.hits[0]
        tail = f"; could not read {len(scan.cant)}: {scan.cant[0]}" if scan.cant else ""
        print(f"RED: {len(scan.hits)} hit(s), first {w}:{n}: [{t}]{tail}")
        return 1
    if scan.text == 0:
        print(f"RED: {read}: decoded zero files as text, so blind to the repository it guards")
        return 1
    if scan.cant:
        print(f"CAN'T TELL: {len(scan.cant)} file(s) unreadable, first {scan.cant[0]} · {read}")
        return 2
    print(f"GREEN · {read} · against {list_name} · {skipped_text(scan)}")
    return 0


def report(scan, read, list_name, why=None):
    for w, n, t in scan.hits:
        print(f"{w}:{n}: [{t}]")
    cant = f"; could not read {len(scan.cant)}: {'; '.join(scan.cant[:3])}" if scan.cant else ""
    if scan.hits:
        print(f"{len(scan.hits)} HIT(S) · {read} · against {list_name}{cant}")
        return 1
    if why or scan.cant:
        print(f"CAN'T TELL ({why or 'unreadable input'}) · {read} · against {list_name}{cant}")
        return 2
    print(f"CLEAN · {read} · against {list_name}")
    return 0


def mode_files(paths, terms, list_name):
    scan = Scan(terms)
    if not paths:
        return report(scan, "read 0 files", list_name, "no file was given")
    for p in paths:
        scan.scan_name(p)
        if os.path.islink(p):
            scan.scan_bytes(p, os.readlink(p).encode("utf-8", "replace"), p)
            continue
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError as e:
            scan.cant.append(f"{p}: {e.strerror or e.__class__.__name__}")
            continue
        scan.scan_bytes(p, data, p)
    read = f"read {scan.text} files as text, {scan.binary} binary counted"
    return report(scan, read, list_name)


def mode_stdin(terms, list_name):
    scan = Scan(terms)
    data = sys.stdin.buffer.read()
    scan.scan_bytes("stdin.txt", data, "stdin")
    return report(scan, f"read {len(data)} bytes from standard input", list_name)


def mode_history(repo, terms, list_name):
    scan = Scan(terms)
    state = {"paths": set(), "blobs": set()}
    commits = tags = 0
    store = None
    try:
        revs = git(["rev-list", "--all"], repo).decode().split()
        if not revs:
            return report(scan, "read 0 commits", list_name, "no commit is reachable from any ref")
        store = Store(repo)
        for oid in revs:
            scan_commit(repo, store, oid, scan, state)
            commits += 1
        refs = git(["for-each-ref", "--format=%(objecttype) %(objectname)", "refs/tags"], repo)
        for line in refs.decode().split("\n"):
            if line.startswith("tag "):
                oid = line.split()[1]
                scan.scan_text(store.read(oid)[1].decode("utf-8", "replace"), f"tag {oid[:12]}")
                tags += 1
        store.close()
    except CannotLook as e:
        return report(scan, f"read {commits} commits before stopping", list_name, str(e))
    read = (f"read {commits} commits, {scan.text} files, {scan.binary} binary counted, {tags} tags"
            f" · {skipped_text(scan)}")
    return report(scan, read, list_name)


def mode_prepush(terms, list_name):
    scan = Scan(terms)
    state = {"paths": set(), "blobs": set()}
    done = set()
    lines = [l for l in sys.stdin.read().split("\n") if l.strip()]
    commits = deletions = tags = 0
    if not lines:
        return report(scan, "nothing pushed (git gave no lines)", list_name)
    repo = os.getcwd()
    store = None
    try:
        for line in lines:
            if len(line.split()) != 4:
                raise CannotLook(f"a pre-push line is not four fields: {len(line.split())} found")
        store = Store(repo)
        for line in lines:
            lref, lid, rref, rid = line.split()
            if lid == ZERO:
                deletions += 1
                continue
            typ = git(["cat-file", "-t", lid], repo).decode().strip()
            if typ == "tag":
                scan.scan_text(store.read(lid)[1].decode("utf-8", "replace"), f"tag {lid[:12]}")
                tags += 1
            target = git(["rev-parse", lid + "^{}"], repo).decode().strip()
            if git(["cat-file", "-t", target], repo).decode().strip() != "commit":
                continue
            if rid == ZERO:
                revs = git(["rev-list", target], repo).decode().split()
            else:
                if subprocess.run(["git", "cat-file", "-e", rid + "^{commit}"], cwd=repo,
                                  capture_output=True).returncode != 0:
                    raise CannotLook(f"the remote's id {rid[:12]} for {rref} is not held here")
                revs = git(["rev-list", f"{rid}..{target}"], repo).decode().split()
            for oid in revs:
                if oid in done:
                    continue
                done.add(oid)
                scan_commit(repo, store, oid, scan, state)
                commits += 1
        store.close()
    except CannotLook as e:
        return report(scan, f"read {commits} commits before stopping", list_name, str(e))
    if commits == 0 and tags == 0 and deletions:
        return report(scan, f"{deletions} deletion(s) counted, nothing pushed to scan", list_name)
    read = (f"read {commits} commits, {scan.text} files, {scan.binary} binary counted, {tags} tags,"
            f" {deletions} deletions counted · {skipped_text(scan)}")
    return report(scan, read, list_name)


# ---------------------------------------------------------------- self-test

FIX = os.path.join(HERE, "tests", "push_scan")


def fixture(name, binary=False):
    with open(os.path.join(FIX, name), "rb") as f:
        data = f.read()
    return data if binary else data.decode("utf-8").strip("\n")


def scratch_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
    return env


ID = ["-c", "user.name=Self Test", "-c", "user.email=selftest@example.invalid"]


def sg(repo, *args, env=None, data=None):
    p = subprocess.run(["git"] + ID + list(args), cwd=repo, env=env or scratch_env(), input=data,
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"scratch git {args[0]} failed: {p.stderr.decode(errors='replace')}")
    return p.stdout.decode().strip()


def new_repo(base, name):
    repo = os.path.join(base, name)
    os.makedirs(repo)
    sg(repo, "init", "-q", "-b", "main")
    return repo


def put(repo, name, data):
    with open(os.path.join(repo, name), "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def commit_file(repo, name, data, msg="Add a file", env=None):
    put(repo, name, data)
    sg(repo, "add", "--", name, env=env)
    sg(repo, "commit", "-q", "-m", msg, env=env)
    return sg(repo, "rev-parse", "HEAD")


def run_self(args, cwd, stdin=""):
    p = subprocess.run([sys.executable, os.path.abspath(__file__)] + args, cwd=cwd,
                       env=scratch_env(), input=stdin.encode(), capture_output=True, timeout=120)
    return p.returncode, p.stdout.decode("utf-8", "replace").strip()


def selftest():
    results = {"plant": [], "control": [], "other": []}

    def expect(group, label, args, want, cwd, stdin="", grep=None):
        code, out = run_self(args, cwd, stdin)
        last = out.splitlines()[-1] if out else "(no output)"
        ok = code == want and (grep is None or grep in out)
        results[group].append(ok)
        state = {0: "green", 1: "red", 2: "can't tell"}.get(code, f"exit {code}")
        print(f"{'ok  ' if ok else 'FAIL'} · {label} · {state} (want {want}) · {last}")
        return ok

    base = tempfile.mkdtemp(prefix="push-scan-selftest-")
    try:
        new_ref = lambda tip, ref="refs/heads/main": f"{ref} {tip} {ref} {ZERO}\n"
        print("-- file plants, each in --files, --tree and --prepush")
        # plants 01-08 are the file plants; their names come from the folder, since one name
        # carries a sample word and this file must hold none
        file_plants = sorted(n for n in os.listdir(FIX) if re.match(r"plant-0[1-8]-", n))
        for name in file_plants:
            expect("plant", f"{name} --files", ["--files", name], 1, FIX)
            repo = new_repo(base, name + ".repo")
            tip = commit_file(repo, name, fixture(name, binary=True))
            expect("plant", f"{name} --tree", ["--tree"], 1, repo)
            expect("plant", f"{name} --prepush", ["--prepush"], 1, repo, new_ref(tip))

        print("-- repository plants, each in --prepush and --history")
        clean = fixture("control-clean.txt", binary=True)

        def p09(repo):
            return new_ref(commit_file(repo, "more.txt", clean, fixture("plant-09-message.txt")))

        def p10(repo):
            env = scratch_env()
            env.update(GIT_AUTHOR_NAME="Someone", GIT_AUTHOR_EMAIL=fixture("plant-10-author-email.txt"))
            return new_ref(commit_file(repo, "more.txt", clean, "More notes", env=env))

        def p11(repo):
            env = scratch_env()
            env.update(GIT_COMMITTER_NAME=fixture("plant-11-committer.txt"))
            return new_ref(commit_file(repo, "more.txt", clean, "More notes", env=env))

        def p12(repo):
            commit_file(repo, "draft.txt", fixture("plant-12-removed.txt"), "Add a draft")
            sg(repo, "rm", "-q", "draft.txt")
            sg(repo, "commit", "-q", "-m", "Remove the draft")
            return new_ref(sg(repo, "rev-parse", "HEAD"))

        def p13(repo):
            sg(repo, "checkout", "-q", "-b", "feature")
            tip = commit_file(repo, "feature.txt", fixture("plant-13-stale-ref.txt"), "Feature work")
            sg(repo, "update-ref", "refs/remotes/origin/feature", tip)
            return new_ref(tip, "refs/heads/feature")

        def p14(repo):
            sg(repo, "checkout", "-q", "-b", "side")
            commit_file(repo, "side.txt", clean, "Side work")
            sg(repo, "checkout", "-q", "main")
            before = commit_file(repo, "main.txt", clean, "Main work")
            sg(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
            put(repo, "resolved.txt", fixture("plant-14-merge.txt"))
            sg(repo, "add", "resolved.txt")
            sg(repo, "commit", "-q", "-m", "Merge the side work")
            return f"refs/heads/main {sg(repo, 'rev-parse', 'HEAD')} refs/heads/main {before}\n"

        def p15(repo):
            msg = os.path.join(base, "tag-message")
            put(repo, msg, fixture("plant-15-tag.txt"))
            sg(repo, "tag", "-a", "v1", "-F", msg)
            return new_ref(sg(repo, "rev-parse", "v1"), "refs/tags/v1")

        repo_plants = [("plant-09-message", p09), ("plant-10-author-email", p10),
                            ("plant-11-committer", p11), ("plant-12-removed (history)", p12),
                            ("plant-13-stale-ref", p13), ("plant-14-merge", p14),
                            ("plant-15-tag", p15)]
        for name, build in repo_plants:
            repo = new_repo(base, name.split()[0] + ".repo")
            commit_file(repo, "notes.txt", clean, "Start the notes")
            line = build(repo)
            expect("plant", f"{name} --prepush", ["--prepush"], 1, repo, line)
            expect("plant", f"{name} --history", ["--history", "."], 1, repo)

        print("-- controls, each green")
        repo = new_repo(base, "control-clean.repo")
        tip = commit_file(repo, "control-clean.txt", clean, "Start the notes")
        ok = all([expect("other", "control-clean --prepush (a clean first push)", ["--prepush"], 0, repo, new_ref(tip)),
                  expect("other", "control-clean --history", ["--history", "."], 0, repo),
                  expect("other", "control-clean --tree", ["--tree"], 0, repo)])
        results["control"].append(ok)
        repo = new_repo(base, "control-near.repo")
        tip = commit_file(repo, "control-near-miss.txt", fixture("control-near-miss.txt", True))
        ok = all([expect("other", "control-near-miss --files", ["--files", "control-near-miss.txt"], 0, FIX),
                  expect("other", "control-near-miss --tree", ["--tree"], 0, repo),
                  expect("other", "control-near-miss --prepush", ["--prepush"], 0, repo, new_ref(tip))])
        results["control"].append(ok)

        print("-- foldings and list syntax")
        for name, want in [("fold-soft-hyphen.txt", 1), ("fold-zwj.txt", 1),
                           ("fold-superscript.txt", 1), ("list-w-inside.txt", 0),
                           ("list-w-alone.txt", 1), ("list-comment-only.txt", 0)]:
            expect("other", name, ["--files", name], want, FIX)

        print("-- twin: blind is never green")
        repo = new_repo(base, "twin-binary.repo")
        commit_file(repo, "case-binary.bin", fixture("case-binary.bin", True))
        expect("other", "twin --tree, every tracked file binary", ["--tree"], 1, repo, grep="zero files")
        repo = new_repo(base, "twin-empty.repo")
        expect("other", "twin --tree, nothing tracked", ["--tree"], 1, repo, grep="zero files")
        expect("other", "twin-list-empty.txt as the list", ["--list", "twin-list-empty.txt", "--files",
               "control-clean.txt"], 2, FIX)
        expect("other", "--files with no file", ["--files"], 2, FIX)
        expect("other", "--history with no commit", ["--history", "."], 2, repo)

        print("-- unreadable input")
        expect("other", "a pre-push line of two fields", ["--prepush"], 2, FIX, "refs/heads/main abc\n")
        expect("other", "a push of a deletion alone", ["--prepush"], 0, FIX,
               f"(delete) {ZERO} refs/heads/old {'1' * 40}\n", grep="deletion")

        print("-- read as text, or not")
        expect("other", "case-nul-in-text.toml (stray NUL, text extension)", ["--files",
               "case-nul-in-text.toml"], 1, FIX)
        expect("other", "case-binary.bin (counted, not scanned)", ["--files", "case-binary.bin"], 0,
               FIX, grep="1 binary counted")
        expect("other", "case-utf16be-nomark.txt", ["--files", "case-utf16be-nomark.txt"], 1, FIX)
        links = os.path.join(base, "links")
        os.makedirs(links)
        os.symlink(fixture("case-link-target.txt"), os.path.join(links, "link"))
        expect("other", "a link whose target names a word", ["--files", "link"], 1, links)
        expect("other", "case-undecodable.txt alone", ["--files", "case-undecodable.txt"], 2, FIX)
        expect("other", "a hit beside case-undecodable.txt", ["--files", "plant-01-tip.txt",
               "case-undecodable.txt"], 1, FIX, grep="could not read")

        print("-- the MANIFEST may name only the sample list and the fixtures folder")
        repo = new_repo(base, "manifest.repo")
        os.makedirs(os.path.join(repo, "checks", "tests", "push_scan"))
        put(repo, MANIFEST_REL, fixture("case-manifest-outside.txt"))
        put(repo, "README.md", fixture("plant-01-tip.txt"))
        sg(repo, "add", ".")
        sg(repo, "commit", "-q", "-m", "A manifest that names a file outside")
        expect("other", "case-manifest-outside.txt --tree", ["--tree"], 1, repo, grep="entry outside")

        print("-- the sample hook, in a scratch clone with a scratch remote")
        remote = os.path.join(base, "remote.git")
        sg(base, "init", "-q", "--bare", "-b", "main", remote)
        clone = os.path.join(base, "clone")
        sg(base, "clone", "-q", remote, clone)
        with open(os.path.join(HERE, "hook-pre-push.sample"), encoding="utf-8") as f:
            hook = f.read()
        hook = hook.replace("__PATH_TO_PUSH_SCAN_PY__", os.path.abspath(__file__))
        hook = hook.replace("__PATH_TO_WORD_LIST__", SAMPLE)
        hook_path = os.path.join(clone, ".git", "hooks", "pre-push")
        put(clone, hook_path, hook)
        os.chmod(hook_path, 0o755)
        commit_file(clone, "notes.txt", clean, "Start the notes")
        p1 = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=clone, env=scratch_env(),
                            capture_output=True)
        commit_file(clone, "plant-01-tip.txt", fixture("plant-01-tip.txt", True), "Add a note")
        p2 = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=clone, env=scratch_env(),
                            capture_output=True)
        remote_tip = sg(remote, "rev-parse", "main")
        clean_ok = p1.returncode == 0
        refused = p2.returncode != 0 and remote_tip != sg(clone, "rev-parse", "HEAD")
        results["other"] += [clean_ok, refused]
        print(f"{'ok  ' if clean_ok else 'FAIL'} · hook: a clean push goes through")
        print(f"{'ok  ' if refused else 'FAIL'} · hook: a push carrying a sample word is refused")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    plants_red = sum(results["plant"])
    plant_cases = len(results["plant"])
    controls = sum(results["control"])
    others = sum(results["other"])
    planted = len(file_plants) + len(repo_plants)
    print(f"plants: {planted} planted ({len(file_plants)} file, {len(repo_plants)} repository),"
          f" {plants_red} of {plant_cases}"
          " plant runs red as expected")
    print(f"controls: {controls} of 2 green in every mode · history: the removed-file plant is"
          f" found · hook: refuses the plant, passes the clean push · other cases: {others} of"
          f" {len(results['other'])} as expected")
    passed = planted == 15 and plants_red == plant_cases == 38 and controls == 2 and others == len(results["other"])
    print(f"selftest: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main(argv):
    args = [a for a in argv if a != "--no-log"]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    list_path, list_name = SAMPLE, SAMPLE_REL
    if "--list" in args:
        i = args.index("--list")
        if i + 1 >= len(args):
            print("CAN'T TELL (--list names no file)")
            return 2
        list_path = list_name = args[i + 1]
        del args[i:i + 2]
    mode, rest = args[0], args[1:]
    if mode == "--selftest":
        return selftest()
    if mode == "--tree":
        return mode_tree(list_path, list_name)
    try:
        terms = load_list(list_path)
    except CannotLook as e:
        print(f"CAN'T TELL ({e}) · read nothing · against {list_name}")
        return 2
    if mode == "--files":
        return mode_files(rest, terms, list_name)
    if mode == "--stdin":
        return mode_stdin(terms, list_name)
    if mode == "--history":
        if len(rest) != 1:
            print("CAN'T TELL (--history takes one repository) · read nothing")
            return 2
        return mode_history(rest[0], terms, list_name)
    if mode == "--prepush":
        return mode_prepush(terms, list_name)
    print(f"CAN'T TELL (unknown mode {mode}; see --help)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
