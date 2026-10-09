from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "workpilot.api:app",
        host=os.getenv("WORKPILOT_HOST", "127.0.0.1"),
        port=int(os.getenv("WORKPILOT_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()

