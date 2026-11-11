"""Install dependencies only after requirements change, not on every launch."""
from pathlib import Path
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
reqs = [ROOT / "requirements.txt", ROOT / "requirements-ui.txt"]
expected = hashlib.sha256(b"".join(p.read_bytes() for p in reqs)).hexdigest()
stamp = ROOT / ".venv" / ".dependencies.sha256"
if stamp.exists() and stamp.read_text(encoding="ascii").strip() == expected:
    sys.exit(0)
for requirements in reqs:
    print(f"Installing: {requirements.name}", flush=True)
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
    if result.returncode:
        print("Dependency installation failed. Check your internet connection and pip output.", flush=True)
        sys.exit(result.returncode)
stamp.write_text(expected, encoding="ascii")
