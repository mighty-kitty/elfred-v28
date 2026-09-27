from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    output = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(output.get(key), dict):
            output[key] = merge(output[key], value)
        else:
            output[key] = value
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Generate a complete Elfred runtime config from unmodified FreeTodo defaults")
    parser.add_argument("--source", type=Path, default=root / "third_party" / "FreeTodo" / "lifetrace" / "config" / "default_config.yaml")
    parser.add_argument("--overrides", type=Path, default=Path(__file__).resolve().parents[2] / "config" / "freetodo_elfred_overrides.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    override = json.loads(args.overrides.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(merge(base, override), allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
