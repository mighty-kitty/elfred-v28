from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory_system.workflow import build_default_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Export interaction logs into an offline review dataset.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--user-id", type=str, default=None)
    args = parser.parse_args()

    agent = build_default_agent()
    payload = agent.repository.export_offline_review_dataset(limit=args.limit, user_id=args.user_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
