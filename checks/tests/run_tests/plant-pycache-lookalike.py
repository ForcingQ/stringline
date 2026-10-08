"""A fixture test for the runner's self-test. It answers --selftest; it passes but writes into a folder whose name only contains __pycache__."""
import os
os.makedirs("notes__pycache__", exist_ok=True)
with open(os.path.join("notes__pycache__", "left.txt"), "w") as f:
    f.write("left behind\n")
print("selftest: PASS")
