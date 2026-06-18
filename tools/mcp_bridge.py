"""
MCP bridge — connects opencode (stdio) to a running Zarin Engine editor (TCP).

Usage (opencode config):
    "zarin-engine": {
        "command": ["python", "tools/mcp_bridge.py"],
        "cwd": "/path/to/ZarinEngine"
    }

Then start the engine editor normally:  python main.py
"""

import asyncio
import json
import sys
import os

HOST = os.environ.get("ZARIN_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZARIN_MCP_PORT", "9100"))


def _read_stdin_line() -> str:
    return sys.stdin.readline()


def _read_stdin_n(n: int) -> str:
    parts = []
    remaining = n
    while remaining > 0:
        chunk = sys.stdin.read(remaining)
        if not chunk:
            break
        parts.append(chunk)
        remaining -= len(chunk)
    return "".join(parts)


async def bridge():
    """Forward stdio MCP (Content-Length framing) ↔ TCP (newline JSON)."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), timeout=5
        )
    except (ConnectionRefusedError, OSError, TimeoutError):
        msg = f"Cannot connect to engine at {HOST}:{PORT}. Start the engine editor first (python main.py)."
        encoded = msg.encode("utf-8")
        sys.stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n{msg}")
        sys.stdout.flush()
        return

    async def stdin_to_tcp():
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, _read_stdin_line)
            if not line:
                break
            hdr = line.strip()
            if not hdr or ":" not in hdr:
                continue
            key, val = hdr.split(":", 1)
            if key.strip().lower() != "content-length":
                continue
            content_length = int(val.strip())
            await asyncio.get_event_loop().run_in_executor(None, _read_stdin_line)
            body = await asyncio.get_event_loop().run_in_executor(None, _read_stdin_n, content_length)
            writer.write((body + "\n").encode("utf-8"))
            await writer.drain()

    async def tcp_to_stdout():
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8").strip()
            if not text:
                continue
            encoded = text.encode("utf-8")
            sys.stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n{text}")
            sys.stdout.flush()

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(stdin_to_tcp())
            tg.create_task(tcp_to_stdout())
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def main():
    asyncio.run(bridge())


if __name__ == "__main__":
    main()
