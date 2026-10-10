#!/usr/bin/env python3
"""Copy q61 production data into the project without changing the source folder.

Extensionless quarterly files are verified Parquet (PAR1) and copied with .parquet
suffix so the existing file loader can detect them. Never commit copied data.
"""
from pathlib import Path
import shutil

SOURCE = Path("/Users/macbookpro/Downloads/q61_extracted/home/cloudshell-user/my-bucket-data")
DEST = Path(__file__).resolve().parent / "data/production/q61"
if not SOURCE.is_dir():
    raise SystemExit(f"Production folder not found: {SOURCE}")
if DEST.is_symlink():
    raise SystemExit(f"Remove existing symlink first: {DEST} (rm data/production/q61)")
DEST.mkdir(parents=True, exist_ok=True)
counts = {"json": 0, "parquet": 0, "renamed_parquet": 0, "skipped": 0}
for src in SOURCE.rglob("*"):
    if not src.is_file():
        continue
    suffix = src.suffix.lower()
    rename = suffix == "" and src.read_bytes()[:4] == b"PAR1"
    if suffix not in (".json", ".parquet") and not rename:
        counts["skipped"] += 1
        continue
    rel = src.relative_to(SOURCE)
    if rename:
        rel = rel.with_name(rel.name + ".parquet")
        counts["renamed_parquet"] += 1
    else:
        counts[suffix[1:]] += 1
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
print("Copied to", DEST)
print(counts)
print("IMPORTANT: Add data/production/ to .gitignore before any git add")
