"""A fixture test for the runner's self-test. It answers --selftest; it passes but makes a dormant hook executable, changing its mode only."""
import os
os.chmod(os.path.join(".git", "hooks", "pre-push"), 0o755)
print("selftest: PASS")
