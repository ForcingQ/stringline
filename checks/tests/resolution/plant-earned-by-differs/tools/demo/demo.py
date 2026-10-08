"""A demo tool for the resolution self-test: it prints its own card's hand-kept copies."""
import sys
FILES = ["tools/demo/demo.py"]
EARNED = 'Something else earned it.'
CATCHING = ["found"]
if "--files" in sys.argv:
    print("\n".join(FILES))
elif "--earned-by" in sys.argv:
    print(EARNED)
elif "--catching" in sys.argv:
    print("\n".join(CATCHING)) if CATCHING else None
