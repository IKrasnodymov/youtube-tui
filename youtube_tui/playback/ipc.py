from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Optional


class MpvIPCError(RuntimeError):
    pass


class MpvIPC:
    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._next_request_id: int = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._observers: dict[int, asyncio.Queue[tuple[str, Any]]] = {}
        self._observer_names: dict[int, str] = {}
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def connect(self, *, retries: int = 30, delay_s: float = 0.1) -> None:
        last_err: Optional[BaseException] = None
        for _ in range(max(1, retries)):
            try:
                reader, writer = await asyncio.open_unix_connection(str(self._socket_path))
                self._reader = reader
                self._writer = writer
                self._reader_task = asyncio.create_task(self._read_loop())
                return
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                last_err = e
                await asyncio.sleep(delay_s)
        raise MpvIPCError(
            f"could not connect to mpv ipc at {self._socket_path}: {last_err!r}"
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._writer is not None:
            try:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except Exception:
                    pass
            except Exception:
                pass
            self._writer = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MpvIPCError("ipc closed"))
        self._pending.clear()
        for q in self._observers.values():
            # Best-effort wake any consumers; sentinel not required since callers cancel.
            try:
                q.put_nowait(("__closed__", None))
            except Exception:
                pass

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if "request_id" in msg:
                    rid = msg.get("request_id")
                    if isinstance(rid, int) and rid in self._pending:
                        fut = self._pending.pop(rid)
                        if fut.done():
                            continue
                        err = msg.get("error")
                        if err == "success":
                            fut.set_result(msg.get("data"))
                        else:
                            fut.set_exception(
                                MpvIPCError(f"mpv error: {err!r} (msg={msg!r})")
                            )
                    continue
                event = msg.get("event")
                if event == "property-change":
                    obs_id = msg.get("id")
                    name = msg.get("name")
                    data = msg.get("data")
                    if isinstance(obs_id, int) and obs_id in self._observers:
                        q = self._observers[obs_id]
                        key = name if isinstance(name, str) else self._observer_names.get(obs_id, "")
                        try:
                            q.put_nowait((key, data))
                        except asyncio.QueueFull:
                            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MpvIPCError("ipc connection lost"))
            self._pending.clear()

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._writer is None or self._closed:
            raise MpvIPCError("ipc not connected")
        data = (json.dumps(payload) + "\n").encode("utf-8")
        async with self._write_lock:
            self._writer.write(data)
            await self._writer.drain()

    async def command(self, *args: Any, timeout_s: float = 2.0) -> Any:
        if self._closed:
            raise MpvIPCError("ipc closed")
        rid = self._next_request_id
        self._next_request_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[rid] = fut
        try:
            await self._send({"command": list(args), "request_id": rid})
        except Exception:
            self._pending.pop(rid, None)
            raise
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            self._pending.pop(rid, None)
            raise MpvIPCError(f"mpv command timed out: {args!r}") from exc

    async def pause(self) -> None:
        await self.set_property("pause", True)

    async def play(self) -> None:
        await self.set_property("pause", False)

    async def toggle_pause(self) -> None:
        await self.command("cycle", "pause")

    async def seek(self, seconds: float, *, mode: str = "relative") -> None:
        await self.command("seek", seconds, mode)

    async def get_property(self, name: str) -> Any:
        return await self.command("get_property", name)

    async def set_property(self, name: str, value: Any) -> None:
        await self.command("set_property", name, value)

    async def quit(self) -> None:
        try:
            await self.command("quit")
        except MpvIPCError:
            pass

    async def observe(self, *names: str) -> AsyncIterator[tuple[str, Any]]:
        if not names:
            return
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        ids: list[int] = []
        for name in names:
            obs_id = self._next_request_id
            self._next_request_id += 1
            self._observers[obs_id] = queue
            self._observer_names[obs_id] = name
            ids.append(obs_id)
            try:
                await self.command("observe_property", obs_id, name)
            except Exception:
                self._observers.pop(obs_id, None)
                self._observer_names.pop(obs_id, None)
                raise
        try:
            while True:
                item = await queue.get()
                if item[0] == "__closed__":
                    return
                yield item
        finally:
            for obs_id in ids:
                self._observers.pop(obs_id, None)
                self._observer_names.pop(obs_id, None)
                if not self._closed:
                    try:
                        await self.command("unobserve_property", obs_id)
                    except Exception:
                        pass
