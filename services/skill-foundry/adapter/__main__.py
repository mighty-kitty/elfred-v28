from __future__ import annotations

import uvicorn

from adapter.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run("adapter.api:create_app", host=settings.host, port=settings.port, reload=False, factory=True)


if __name__ == "__main__":
    main()
