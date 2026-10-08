"""A fixture test for the runner's self-test. It answers --selftest; it dies on a signal, an exit code outside 0, 1 and 2."""
import os
import signal
import sys
print("fixture case: about to stop on a signal")
sys.stdout.flush()
os.kill(os.getpid(), signal.SIGTERM)
