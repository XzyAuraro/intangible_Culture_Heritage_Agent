import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

import websockets


ROOT = Path(__file__).parent
SERVER_SCRIPT = ROOT / "stackchan_mcp_server.py"
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 60


def load_local_env() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("XIAOZHI_MCP_BRIDGE")


def endpoint_from_env() -> str:
    endpoint = os.getenv("XIAOZHI_MCP_ENDPOINT") or os.getenv("MCP_ENDPOINT") or ""
    if not endpoint:
        raise RuntimeError("请先在 .env.local 或环境变量中设置 XIAOZHI_MCP_ENDPOINT。")
    return endpoint


async def pipe_websocket_to_process(websocket, process: subprocess.Popen) -> None:
    while True:
        message = await websocket.recv()
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        if process.stdin is None:
            raise RuntimeError("MCP server stdin is unavailable")
        process.stdin.write(message + "\n")
        process.stdin.flush()


async def pipe_process_to_websocket(process: subprocess.Popen, websocket) -> None:
    if process.stdout is None:
        raise RuntimeError("MCP server stdout is unavailable")
    while True:
        data = await asyncio.to_thread(process.stdout.readline)
        if not data:
            raise RuntimeError("MCP server process ended")
        await websocket.send(data)


async def pipe_stderr(process: subprocess.Popen) -> None:
    if process.stderr is None:
        return
    while True:
        data = await asyncio.to_thread(process.stderr.readline)
        if not data:
            return
        sys.stderr.write(data)
        sys.stderr.flush()


async def connect_once(endpoint: str) -> None:
    logger.info("Connecting StackChan text-only MCP guide service...")
    async with websockets.connect(endpoint) as websocket:
        logger.info("Connected. StackChan MCP page should show Online.")
        process = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            text=True,
            env=os.environ.copy(),
        )
        try:
            await asyncio.gather(
                pipe_websocket_to_process(websocket, process),
                pipe_process_to_websocket(process, websocket),
                pipe_stderr(process),
            )
        finally:
            logger.info("Stopping local MCP server process.")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


async def run_forever() -> None:
    endpoint = endpoint_from_env()
    backoff = INITIAL_BACKOFF_SECONDS
    while True:
        try:
            await connect_once(endpoint)
            backoff = INITIAL_BACKOFF_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("MCP bridge disconnected: %s. Reconnecting in %ss.", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def stop(*_args) -> None:
    logger.info("Stopping StackChan MCP bridge.")
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("Stopped.")
