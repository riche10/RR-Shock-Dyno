"""Build the preservation archive and verify every included file."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
verification = root / "Verification"
inventory = json.loads((verification / "Original file inventory.json").read_text(encoding="utf-8"))
snapshot = root / "RR ShockDyno"
original = Path(inventory["original_path"])
for record in inventory["files"]:
    if original.is_dir():
        assert hashlib.sha256((original / record["path"]).read_bytes()).hexdigest() == record["sha256"], record["path"]
    if record["included_in_snapshot"]:
        assert hashlib.sha256((snapshot / record["path"]).read_bytes()).hexdigest() == record["sha256"], record["path"]
results = json.loads((verification / "Software verification.json").read_text(encoding="utf-8"))
assert len(results["passed_checks"]) == 11 and not results["hardware_tested"]

output = root / "Shock Dyno - Source and Technical Handoff.zip"
manifest = verification / "SHA256SUMS.json"
files = sorted(path for path in root.rglob("*") if path.is_file()
               and ".verification" not in path.relative_to(root).parts
               and path not in (output, manifest) and path.name != "Drive upload receipt.txt")
records = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]
manifest.write_text(json.dumps({"source_changed": False, "hardware_tested": False, "files": records}, indent=2), encoding="utf-8")
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in [*files, manifest]:
        archive.write(path, path.relative_to(root).as_posix())
    for directory in inventory["directories_in_snapshot"]:
        path = snapshot / directory
        if not any(path.iterdir()):
            archive.writestr("RR ShockDyno/" + directory + "/", b"")
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    for record in records:
        assert hashlib.sha256(archive.read(record["path"])).hexdigest() == record["sha256"]
print(json.dumps({"zip": str(output), "files": len(files) + 1,
    "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "original_project_files_verified": sum(r["included_in_snapshot"] for r in inventory["files"])}))
