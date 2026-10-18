"""Load the NASS API key from the repo-root .env at runtime. The key is never printed or written anywhere."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


def load_key() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.environ.get("NASS_API_KEY")
    if not key:
        raise SystemExit("NASS_API_KEY not found: put it in the repo-root .env file")
    return key


def redact(text: str, key: str) -> str:
    """Remove the key from any message before it is printed or saved (requests puts the URL in its errors)."""
    return str(text).replace(key, "***NASS_API_KEY***")
