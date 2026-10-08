#!/usr/bin/env python3
"""Check 1 · currency: no released card is behind the tool it describes.

What it compares: for each `released` card under manual/tools/, its stamp (`verified_against`)
against the commits since. The stamp must be a full 40-character commit id the repository
holds and an ancestor of the current commit; every path in `files` must be tracked
(`git ls-files`); then `git log <stamp>..HEAD -- <files>` must list no commit.
How it is fired: by checks/run_all.py on every push and pull request (the workflow, with full
history fetched), and by hand, `python3 checks/currency.py`. It reports; it never stops work.
The failure that earned it: a manual drifts behind its code silently; in the owner's earlier
manual the stamp was the only thing that made a re-read due, and a reviewer showed that a
symbolic stamp (a branch name, HEAD) or a stamp from a branch never merged stays green forever.
Its twin: a manual/ folder with no cards is RED; a missing manual/ is CAN'T TELL (a branch
building the checks before the corpus exists sees can't tell, not red); zero released with n
building is GREEN and says so, so the building phase is neither blind nor permanently red.
What it does not prove: that a card is right; only that someone re-read it after the last change
to its files. It cannot look at a shallow clone (CAN'T TELL), and it treats any git error, or a
warning on standard error with exit 0, as CAN'T TELL; a status other than
building or released is CAN'T TELL naming the card and the value. It needs merges that never rewrite history.

Output, one line: `GREEN · read ...`, `RED: <card>: <what>` or `CAN'T TELL: <what>`; exit 0/1/2.
  currency.py [--root DIR]    DIR defaults to the folder above checks/
  currency.py --selftest      scratch repositories built from checks/tests/currency/
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class CantTell(Exception):
    pass


def git(root, *args, ok=(0,)):
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off"] + list(args), cwd=root,
                           capture_output=True, text=True)
    except OSError as e:
        raise CantTell(f"git could not run: {e}")
    err = p.stderr.strip()
    if p.returncode not in ok:
        raise CantTell(f"git {args[0]} exited {p.returncode}: {err.splitlines()[-1] if err else 'no message'}")
    if err and p.returncode == 0:
        raise CantTell(f"git {args[0]} warned: {err.splitlines()[0]}")
    return p.returncode, p.stdout


def run(root):
    manual = os.path.join(root, "manual")
    if not os.path.isdir(manual):
        return "CAN'T TELL: no manual/ folder on this tree, so no cards to read", 2
    paths = sorted(glob.glob(os.path.join(manual, "tools", "*.toml")))
    if not paths:
        return "RED: manual/: the folder exists and holds no cards (manual/tools/*.toml)", 1
    try:
        if git(root, "rev-parse", "--is-shallow-repository")[1].strip() != "false":
            return "CAN'T TELL: a shallow clone; the commits since a stamp cannot be read", 2
        tracked = set(git(root, "ls-files", "-z")[1].split("\0"))
        reds, cants, released, building = [], [], 0, 0
        for p in paths:
            rel = os.path.relpath(p, root)
            try:
                with open(p, "rb") as f:
                    card = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError) as e:
                cants.append(f"{rel}: unreadable ({e.__class__.__name__})")
                continue
            status = card.get("status")
            if status not in ("building", "released"):
                cants.append(f"{rel}: status {status!r} is neither building nor released")
                continue
            if status == "building":
                building += 1
                continue
            released += 1
            files = card.get("files")
            stamp = card.get("verified_against")
            if not isinstance(files, list) or not files:
                reds.append(f"{rel}: released with no files to watch")
                continue
            missing = [f for f in files if f not in tracked]
            if missing:
                reds.append(f"{rel}: files names {missing[0]}, which git does not track")
                continue
            if not isinstance(stamp, str) or not HEX40.match(stamp):
                cants.append(f"{rel}: stamp {stamp!r} is not a full 40-character commit id")
                continue
            if git(root, "cat-file", "-e", stamp + "^{commit}", ok=(0, 1, 128))[0] != 0:
                cants.append(f"{rel}: stamp {stamp[:12]} is not a commit this repository holds")
                continue
            if git(root, "merge-base", "--is-ancestor", stamp, "HEAD", ok=(0, 1))[0] != 0:
                cants.append(f"{rel}: stamp {stamp[:12]} is not an ancestor of the current commit")
                continue
            since = git(root, "log", "--format=%H", f"{stamp}..HEAD", "--", *files)[1].split()
            if since:
                reds.append(f"{rel}: {len(since)} commit(s) to its files since its stamp, latest {since[0][:12]}")
    except CantTell as e:
        return f"CAN'T TELL: {e}", 2
    if reds:
        more = f"; {len(reds) + len(cants) - 1} more card(s) not green" if len(reds) + len(cants) > 1 else ""
        return f"RED: {reds[0]}{more}", 1
    if cants:
        more = f"; {len(cants) - 1} more" if len(cants) > 1 else ""
        return f"CAN'T TELL: {cants[0]}{more}", 2
    return (f"GREEN · read {len(paths)} cards: {released} released, {building} building · against"
            f" the commits since each released card's stamp"), 0


# ---------------------------------------------------------------- self-test

def selftest():
    fix = os.path.join(HERE, "tests", "currency")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    ident = ["-c", "user.name=Self Test", "-c", "user.email=selftest@example.invalid"]
    base = tempfile.mkdtemp(prefix="currency-selftest-")

    def sg(repo, *args):
        p = subprocess.run(["git"] + ident + list(args), cwd=repo, env=env, capture_output=True,
                           text=True)
        if p.returncode != 0:
            raise RuntimeError(f"scratch git {args[0]}: {p.stderr}")
        return p.stdout.strip()

    def text(name):
        with open(os.path.join(fix, name), encoding="utf-8") as f:
            return f.read()

    def write(repo, rel, body):
        os.makedirs(os.path.dirname(os.path.join(repo, rel)), exist_ok=True)
        with open(os.path.join(repo, rel), "w", encoding="utf-8") as f:
            f.write(body)

    def commit(repo, msg, *rels):
        sg(repo, "add", "--", *rels)
        sg(repo, "commit", "-q", "-m", msg)
        return sg(repo, "rev-parse", "HEAD")

    def repo_with(name, card_fixture, stamp_from="tool", extra=None):
        """A tool commit, then the card stamped with it, then the case's own change."""
        repo = os.path.join(base, name)
        os.makedirs(repo)
        sg(repo, "init", "-q", "-b", "main")
        write(repo, "tools/demo/demo.py", text("demo-v1.py"))
        tool = commit(repo, "The tool", "tools/demo/demo.py")
        stamp = tool
        if stamp_from == "unmerged":
            sg(repo, "checkout", "-q", "-b", "side")
            write(repo, "notes.txt", "side work\n")
            stamp = commit(repo, "Side work, never merged", "notes.txt")
            sg(repo, "checkout", "-q", "main")
        if card_fixture:
            write(repo, "manual/tools/demo.toml", text(card_fixture).replace("{stamp}", stamp))
            commit(repo, "The card", "manual/tools/demo.toml")
        if extra:
            extra(repo, stamp)
        return repo

    def changed(repo, stamp):
        write(repo, "tools/demo/demo.py", text("demo-v2.py"))
        commit(repo, "Change the tool after its stamp", "tools/demo/demo.py")

    def second_building(repo, stamp):
        write(repo, "manual/tools/other.toml", text("control-building.toml").replace("demo", "other"))
        commit(repo, "A second building card", "manual/tools/other.toml")

    def ambiguous(repo, stamp):
        sg(repo, "branch", stamp)  # a ref named like the stamp: git warns, and exits 0

    def site_only(repo, stamp):
        write(repo, "manual/site.toml", text("twin-site.toml"))
        commit(repo, "A manual with no cards", "manual/site.toml")

    cases = [
        ("control-current.toml", 0, None, "tool", None),
        ("control-building.toml (two building cards)", 0, "control-building.toml", "tool", second_building),
        ("plant-changed-after-stamp.toml", 1, None, "tool", changed),
        ("plant-missing-file.toml", 1, None, "tool", None),
        ("plant-empty-files.toml", 1, None, "tool", None),
        ("twin-site.toml (a manual/ with no cards)", 1, "", "tool", site_only),
        ("no manual/ folder", 2, "", "tool", None),
        ("cant-tell-symbolic-stamp.toml", 2, None, "tool", None),
        ("cant-tell-unknown-stamp.toml", 2, None, "tool", None),
        ("cant-tell-unmerged-stamp.toml", 2, None, "unmerged", None),
        ("cant-tell-git-warning.toml", 2, None, "tool", ambiguous),
        ("unreadable-card.toml", 2, None, "tool", None),
        ("cant-tell-unknown-status.toml", 2, None, "tool", None),
    ]
    ok_all = True
    try:
        for i, (label, want, fixture, stamp_from, extra) in enumerate(cases):
            fixture = label.split()[0] if fixture is None else fixture
            repo = repo_with(f"case{i}", fixture, stamp_from, extra)
            line, code = run(repo)
            ok = code == want
            ok_all &= ok
            print(f"{'ok  ' if ok else 'FAIL'} · {label} · want {want}, got {code} · {line}")
        shallow = os.path.join(base, "shallow")
        src = repo_with("shallow-source", "control-current.toml", "tool", changed)
        sg(base, "clone", "-q", "--depth", "1", "file://" + src, shallow)
        line, code = run(shallow)
        ok = code == 2
        ok_all &= ok
        print(f"{'ok  ' if ok else 'FAIL'} · a shallow clone of a red case · want 2, got {code} · {line}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
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
