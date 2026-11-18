"""Load project configuration before any module captures environment values."""
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
# Explicit environment settings (including isolated test DBs) always win.
load_dotenv(PROJECT_ROOT / ".env", override=False)
