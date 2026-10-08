"""A fixture test for the runner's self-test. It answers --selftest; it crashes with exit 1."""
print("fixture case: about to break")
raise RuntimeError("the fixture test broke")
