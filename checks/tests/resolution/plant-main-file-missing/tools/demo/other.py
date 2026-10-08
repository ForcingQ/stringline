"""A demo tool for the resolution self-test: it prints its own card's hand-kept copies."""
import sys
FILES = ["tools/demo/other.py"]
EARNED = 'A quote drifted from what was typed, and nothing noticed.'
CATCHING = ["found"]
if "--files" in sys.argv:
    print("\n".join(FILES))
elif "--earned-by" in sys.argv:
    print(EARNED)
elif "--catching" in sys.argv:
    print("\n".join(CATCHING)) if CATCHING else None
