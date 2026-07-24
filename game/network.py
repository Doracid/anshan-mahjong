"""
客户端网络层 — WebSocket 连接封装
"""
from __future__ import annotations
import asyncio
import json
import threading
from typing import Optional, Callable, Dict, Any


class NetworkClient:
    """WebSocket 客户端，在后台线程中运行 asyncio 事件循环"""

    def __init__(self):
        self.ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._url = ""
        self.on_message: Optional[Callable[[dict], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int = 8765):
        """启动后台线程连接服务器"""
        self._url = f"ws://{host}:{port}"
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        """后台线程运行 asyncio 事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._client_loop())

    async def _client_loop(self):
        """WebSocket 客户端主循环"""
        import websockets
        try:
            async with websockets.connect(self._url) as ws:
                self.ws = ws
                self._connected = True
                if self.on_connected:
                    self.on_connected()
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        if self.on_message:
                            self.on_message(msg)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[网络] 连接断开: {e}")
        finally:
            self._connected = False
            self.ws = None
            if self.on_disconnected:
                self.on_disconnected()

    def send(self, msg: dict):
        """发送消息（线程安全）"""
        if self.ws and self._loop and not self._loop.is_closed():
            coro = self.ws.send(json.dumps(msg, ensure_ascii=False))
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def disconnect(self):
        """断开连接"""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._connected = False
        self.ws = None
