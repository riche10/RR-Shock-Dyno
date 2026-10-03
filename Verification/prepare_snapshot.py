"""Preserve the supplied project without changing its files or source code."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
original = Path(r"C:\Users\Omari\Desktop\bajaProjects\RR ShockDyno")
snapshot = root / "RR ShockDyno"
records = []
directories = []
for path in sorted(original.rglob("*")):
    relative = path.relative_to(original)
    included = relative.parts[0] != ".venv"
    if path.is_dir():
        if included:
            (snapshot / relative).mkdir(parents=True, exist_ok=True)
            directories.append(relative.as_posix())
        continue
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    records.append({"path": relative.as_posix(), "bytes": path.stat().st_size,
                    "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "sha256": content_hash, "included_in_snapshot": included})
    if included:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert hashlib.sha256(target.read_bytes()).hexdigest() == content_hash, relative
        else:
            shutil.copy2(path, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == content_hash, relative

metadata_dir = root / "Verification"
metadata_dir.mkdir(exist_ok=True)
(metadata_dir / "Original file inventory.json").write_text(json.dumps({
    "original_path": str(original),
    "snapshot_policy": "All non-.venv files and directories preserved, including IDE and bytecode records. The original .venv is unchanged and inventoried but not packaged.",
    "git_history_present": (original / ".git").exists(),
    "directories_in_snapshot": directories, "files": records,
}, indent=2), encoding="utf-8")
shutil.copy2(original / ".venv/pyvenv.cfg", metadata_dir / "Original pyvenv.cfg.txt")
print(json.dumps({"total_files": len(records),
    "preserved_files": sum(r["included_in_snapshot"] for r in records),
    "environment_files_inventoried_only": sum(not r["included_in_snapshot"] for r in records),
    "preserved_bytes": sum(r["bytes"] for r in records if r["included_in_snapshot"])}))
