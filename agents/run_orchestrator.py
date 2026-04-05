# agents/run_orchestrator.py
"""
PariMarket — Root Orchestrator Entry Point

How to run (all from the PROJECT ROOT — the folder containing pyproject.toml):

  Option 1 — uv scripts (recommended):
    uv run agents

  Option 2 — direct python:
    python agents/run_orchestrator.py

  Option 3 — module style:
    python -m agents.run_orchestrator

DO NOT run as:
    cd agents && python run_orchestrator.py     ← used to work, now requires agents/ on path
Instead always run from the project root.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ── sys.path guard ────────────────────────────────────────────────────────────
# All agent files use flat imports: `from shared.config import ...`
# Those resolve only when the agents/ directory is on sys.path.
#
# Python adds the script's OWN directory to sys.path[0] when you run:
#     python agents/run_orchestrator.py
# So Path(__file__).parent == <project_root>/agents/ → correct.
#
# When uv runs the script via [tool.uv.scripts], the working directory
# is the project root but __file__ still resolves to the agents/ subfolder,
# so the same logic applies.
#
# We normalise to a resolved absolute path and add it if not already present.
_AGENTS_DIR = Path(__file__).resolve().parent
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))
# ─────────────────────────────────────────────────────────────────────────────

# GOOGLE_API_KEY must be in the environment BEFORE importing ADK model classes.
from shared.config import GOOGLE_API_KEY, TICKER_INTERVAL_SECS, validate
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

from google.adk.runners import Runner                   # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types as genai_types           # noqa: E402

from root_orchestrator import root_agent                # noqa: E402

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(name)-28s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("runner")


# ── Single tick ───────────────────────────────────────────────────────────────

async def run_tick(tick_number: int) -> str:
    """
    Execute one complete orchestration tick through the root agent.
    A fresh session is created per tick — no history bleeds between runs.
    """
    session_svc = InMemorySessionService()
    runner      = Runner(
        agent           = root_agent,
        app_name        = "parimarket",
        session_service = session_svc,
    )
    session = await session_svc.create_session(
        app_name = "parimarket",
        user_id  = "scheduler",
    )
    prompt = genai_types.Content(
        role  = "user",
        parts = [genai_types.Part(
            text = (
                f"Scheduled orchestration tick #{tick_number}. "
                "Execute the full 7-step protocol now."
            )
        )],
    )
    parts: list[str] = []
    async for event in runner.run_async(
        user_id     = "scheduler",
        session_id  = session.id,
        new_message = prompt,
    ):
        if event.is_final_response() and event.content:
            for p in event.content.parts:
                if hasattr(p, "text") and p.text:
                    parts.append(p.text)
    return "\n".join(parts)


# ── Health Check Server (Cloud Run) ──────────────────────────────────────────

async def health_check_handler(reader, writer):
    """
    Very simple HTTP handler to satisfy Cloud Run's health check.
    It returns a 200 OK to any request.
    """
    try:
        # Read the request line (we don't care about the content)
        await reader.read(1024)
        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
        writer.write(response.encode())
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def start_health_server():
    """
    Starts a background task that listens on $PORT (default 8080).
    Required for Google Cloud Run deployment.
    """
    port = int(os.environ.get("PORT", "8080"))
    server = await asyncio.start_server(health_check_handler, "0.0.0.0", port)
    log.info("Started health check server on port %d", port)
    async with server:
        await server.serve_forever()


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║        PariMarket Root Orchestrator                  ║")
    print("  ║        Google ADK + Gemini 2.0 Flash                 ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    # Validate all env vars before first tick.
    try:
        validate()
    except (EnvironmentError, ValueError, AssertionError) as exc:
        print(f"\n  ERROR: {exc}")
        sys.exit(1)

    # Start the health check server in the background (for Cloud Run)
    asyncio.create_task(start_health_server())

    print(f"  Tick interval : {TICKER_INTERVAL_SECS}s")
    print()

    tick = 0
    while True:
        tick += 1
        log.info("─── Tick #%d ────────────────────────────────────────", tick)
        t0 = time.monotonic()
        try:
            resp    = await run_tick(tick)
            elapsed = time.monotonic() - t0
            log.info("Tick #%d done in %.1fs", tick, elapsed)
            if resp:
                preview = resp[:500].replace("\n", " ")
                log.info("  └─ %s%s", preview, " …" if len(resp) > 500 else "")
        except Exception as exc:
            elapsed = time.monotonic() - t0
            log.error("Tick #%d FAILED (%.1fs): %s", tick, elapsed, exc, exc_info=True)

        log.info("Sleeping %ds until next tick…", TICKER_INTERVAL_SECS)
        await asyncio.sleep(TICKER_INTERVAL_SECS)


if __name__ == "__main__":
    asyncio.run(main())