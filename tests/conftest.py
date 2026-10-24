import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    """Each test starts with empty Streamlit caches, runs from the repo root and has no real API key."""
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    st.cache_data.clear()
    yield
