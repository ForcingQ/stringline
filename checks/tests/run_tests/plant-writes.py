"""A fixture test for the runner's self-test. It answers --selftest; it passes but writes a file into the tree."""
open("written-by-a-test.txt", "w").write("left behind\n")
print("selftest: PASS")
