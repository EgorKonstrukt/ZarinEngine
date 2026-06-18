"""
MCP stdio ↔ SSE bridge — connects opencode to the running editor's SSE server.

Configure opencode (opencode.jsonc) to run this script:
  "zarin-engine": {
    "type": "local",
    "command": ["python", "zarin_mcp_launcher.py"],
    "cwd": "C:\\Users\\Zarrakun\\PycharmProjects\\ZarinEngine",
    "enabled": true
  }

The Zarin Engine editor with ZarinMCP plugin must already be running.
"""
import os
import anyio
from mcp.client.sse import sse_client
from mcp.server.stdio import stdio_server


HOST = os.environ.get("ZARIN_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZARIN_MCP_PORT", "9100"))
SSE_URL = f"http://{HOST}:{PORT}/sse"


async def main():
    async with (
        stdio_server() as (stdio_read, stdio_write),
        sse_client(SSE_URL) as (sse_read, sse_write),
    ):
        async with anyio.create_task_group() as tg:
            tg.start_soon(_forward, "stdio→sse", stdio_read, sse_write)
            tg.start_soon(_forward, "sse→stdio", sse_read, stdio_write)


async def _forward(label: str, source, dest):
    try:
        async for msg in source:
            if isinstance(msg, Exception):
                continue
            await dest.send(msg)
    except anyio.ClosedResourceError:
        pass


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
