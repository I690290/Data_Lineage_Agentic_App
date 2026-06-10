"""Streamlit app configuration loaded from environment."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

FASTAPI_BASE_URL: str = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
# React frontend (Vite dev server on :3000, or built static served by FastAPI)
LINEAGE_VIEWER_URL: str = os.getenv("LINEAGE_VIEWER_URL", "http://localhost:3000")
# Legacy alias kept for backward compatibility
LINEAGE_DIAGRAM_URL: str = os.getenv("LINEAGE_DIAGRAM_URL", LINEAGE_VIEWER_URL)
STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))
