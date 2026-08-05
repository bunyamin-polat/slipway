import sys
from pathlib import Path

# The scripts are executables, not an installed package, so they are imported the same
# way they run: by putting scripts/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
