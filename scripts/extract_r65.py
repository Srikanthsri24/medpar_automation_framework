"""Safely extract the supplied R65 ZIP (even when named .txt) without changing data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def extract_archive(source, destination):
    """Preserve my_bucket3-relative paths; reject unsafe names and conflicting local files."""
    source, destination = Path(source), Path(destination)
    inventory = []
    with zipfile.ZipFile(source) as archive:
        prepared = []
        for item in archive.infolist():
            if item.is_dir():
                continue
            parts = PurePosixPath(item.filename).parts
            if '..' in parts or PurePosixPath(item.filename).is_absolute() or 'my_bucket3' not in parts:
                raise ValueError(f'Unexpected archive path: {item.filename}')
            relative = Path(*parts[parts.index('my_bucket3') + 1:])
            target = destination / relative
            payload = archive.read(item)
            if target.exists() and target.read_bytes() != payload:
                raise ValueError(f'Existing file differs; refusing overwrite: {relative}')
            prepared.append((relative, target, payload))
        for relative, target, payload in prepared:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(payload)
            inventory.append({'path': relative.as_posix(), 'bytes': len(payload),
                              'sha256': hashlib.sha256(payload).hexdigest()})
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'archive_inventory.json').write_text(json.dumps({
        'archive': source.name, 'archive_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'files': inventory}, indent=2) + '\n')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', default=str(PROJECT_ROOT / 'data/production/r65'))
    args = parser.parse_args()
    files = extract_archive(args.source, args.destination)
    print(f'Extracted and verified {len(files)} files into {args.destination}')
    print(f'Final MEDPAR JSON files: {sum(f["path"].startswith("6-final-processing/") and f["path"].endswith(".json") for f in files)}')
