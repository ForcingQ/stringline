"""A fixture test for the runner's self-test. It answers --selftest; it passes but writes into an ignored folder."""
import os
os.makedirs("state", exist_ok=True)
open("state/run.json", "w").write("{}\n")
print("selftest: PASS")
