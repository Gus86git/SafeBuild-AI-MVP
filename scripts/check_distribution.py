"""Report prohibited distribution files and credential patterns without values."""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", "output"}
PATTERNS = [
    re.compile(rb"gsk_[A-Za-z0-9]{20,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
]


def check(path):
    relative = path.relative_to(ROOT)
    name = path.name.lower()
    prohibited = (
        name in {"secrets.toml", ".env", "authorized.json"}
        or name.startswith(".env.")
        and name != ".env.example"
        or path.suffix.lower() in {".pt", ".safetensors", ".sqlite", ".sqlite3", ".db"}
        or relative.parts[0] in {"data", "models"}
    )
    if prohibited:
        return "prohibited distribution resource"
    if any(pattern.search(path.read_bytes()) for pattern in PATTERNS):
        return "credential pattern; value withheld"
    return None


def main():
    findings = []
    # In a repository check tracked files even if a future ignore rule hides them.
    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        )
        paths = [ROOT / name for name in result.stdout.decode().split("\0") if name]
    else:
        paths = [
            p
            for p in ROOT.rglob("*")
            if p.is_file() and not IGNORED.intersection(p.relative_to(ROOT).parts)
        ]
    for path in paths:
        reason = check(path)
        if reason:
            findings.append(
                {"path": path.relative_to(ROOT).as_posix(), "reason": reason}
            )
    for finding in findings:
        print(f"{finding['path']}: {finding['reason']}")
    print(
        f"Scanned {len(paths)} files; findings: {len(findings)}. Pattern scan is not a complete security audit."
    )
    return bool(findings)


if __name__ == "__main__":
    sys.exit(main())
