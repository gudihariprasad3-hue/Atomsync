"""
pytest conftest.py – shared fixtures and path setup for AtmoSync tests.
"""
import sys
from pathlib import Path

# Make root importable from any test
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
