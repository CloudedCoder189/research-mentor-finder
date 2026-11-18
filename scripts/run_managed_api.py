"""Private-safe operational logs; raw stdout/stderr and access logs are discarded."""
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout = open(os.devnull, "w")
sys.stderr = open(os.devnull, "w")
import runtime_config
from api.retention import Store, PrivateSafeHandler
import uvicorn

store = Store()
logging.basicConfig(level=logging.INFO, handlers=[PrivateSafeHandler(store)], force=True)
uvicorn.run("api.main:app", host="127.0.0.1", port=int(os.getenv("MANAGED_API_PORT", "18501")), proxy_headers=False, access_log=False, log_config=None)
