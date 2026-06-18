"""MCP stdio <-> SSE bridge with async stdin/stdout handling."""
import os
import sys
import anyio
import logging
from mcp.client.sse import sse_client
from mcp.server.stdio import stdio_server

HOST = os.environ.get("ZARIN_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZARIN_MCP_PORT", "9100"))
SSE_URL = f"http://{HOST}:{PORT}/sse"


async def forward(source, dest):
    try:
        async for msg in source:
            if isinstance(msg, Exception):
                continue
            await dest.send(msg)
    except anyio.ClosedResourceError:
        pass


async def main():
    async with (
        stdio_server() as (stdio_read, stdio_write),
        sse_client(SSE_URL) as (sse_read, sse_write),
    ):
        async with anyio.create_task_group() as tg:
            tg.start_soon(forward, stdio_read, sse_write)
            tg.start_soon(forward, sse_read, stdio_write)


if __name__ == "__main__":
    for attempt in range(3):
        try:
            anyio.run(main, backend="asyncio")
            break
        except (ConnectionError, OSError) as e:
            print(f"Connection error (attempt {attempt+1}/3): {e}", file=sys.stderr)
            import time
            time.sleep(3)
            continue
        except Exception as e:
            print(f"Fatal error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        sys.exit(1)
