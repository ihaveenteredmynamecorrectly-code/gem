#!/usr/bin/env python3
"""Run the Gemini free-tier chat app.

Usage:
    uvicorn app.main:app --host 0.0.0.0 --port 12000
or:
    python -m app.run [--host 0.0.0.0] [--port 12000]
"""
import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Gemini free-tier chat app")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "12000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
