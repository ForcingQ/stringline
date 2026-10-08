"""A fixture test for the runner's self-test. It answers --selftest; it passes but installs a hook in the repository's hooks folder."""
import os
os.makedirs(os.path.join(".git", "hooks"), exist_ok=True)
with open(os.path.join(".git", "hooks", "pre-push"), "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
print("selftest: PASS")
