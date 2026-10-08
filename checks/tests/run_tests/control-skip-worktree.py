"""A fixture test for the runner's self-test. It answers --selftest; it marks a tracked file skip-worktree and edits it, a change git status cannot see (a named limit)."""
import subprocess
subprocess.run(["git", "update-index", "--skip-worktree", "notes.txt"], check=True)
with open("notes.txt", "a") as f:
    f.write("an edit git status will not show\n")
print("selftest: PASS")
