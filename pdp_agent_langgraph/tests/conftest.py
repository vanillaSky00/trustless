"""Shared pytest fixtures."""

import os
import sys
from pathlib import Path

# Ensure src/ is on the path even without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Make tests deterministic
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
