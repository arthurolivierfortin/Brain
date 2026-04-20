"""Add scripts/ to sys.path so test files can import brain_wake_up etc."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
