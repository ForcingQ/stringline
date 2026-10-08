"""A fixture test for the runner's self-test. It answers --selftest; it passes but writes into a folder whose name holds a space before __pycache__."""
import os
os.makedirs("FIXTURE __pycache__", exist_ok=True)
with open(os.path.join("FIXTURE __pycache__", "left.txt"), "w") as f:
    f.write("left behind\n")
print("selftest: PASS")
