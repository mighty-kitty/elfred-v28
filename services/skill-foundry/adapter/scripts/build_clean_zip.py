from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "dist", "node_modules"}
EXCLUDED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".pyc", ".env"}


def build(source: Path, output: Path) -> int:
    files = [
        path for path in source.rglob("*")
        if path.is_file()
        and not (set(path.relative_to(source).parts) & EXCLUDED_PARTS)
        and path.suffix not in EXCLUDED_SUFFIXES
        and path.name != output.name
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path, Path(source.name) / path.relative_to(source))
    return len(files)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build a source-only clean delivery ZIP")
    parser.add_argument("--source", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root.parent / "dist" / "elfred_freetodo_adapter_clean.zip")
    args = parser.parse_args()
    count = build(args.source.resolve(), args.output.resolve())
    print(f"{args.output.resolve()} ({count} files)")


if __name__ == "__main__":
    main()
