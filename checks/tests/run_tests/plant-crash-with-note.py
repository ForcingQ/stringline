"""A fixture test for the runner's self-test. It answers --selftest; it crashes on an exception that carries a note, so its traceback ends in two unindented lines."""
print("fixture case: about to break")
error = RuntimeError("the fixture test broke")
error.add_note("a note added to the exception")
raise error
