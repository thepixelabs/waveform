"""
Root conftest — adds the project root to sys.path so the waveform package
is importable without requiring an editable install.
"""
import sys
from pathlib import Path

# Ensure the project root (containing the waveform/ package) is on sys.path
sys.path.insert(0, str(Path(__file__).parent))
