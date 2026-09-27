from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Adapter OpenAPI without starting a server")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

