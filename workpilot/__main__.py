from __future__ import annotations


def main() -> None:
    import uvicorn

    from workpilot.config import Settings

    settings = Settings.from_env()
    uvicorn.run(
        "workpilot.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
