"""WebRTC signalling relay: one phone camera, any number of dashboard viewers.

/ws/signal?role=camera   the phone (/camera page)
/ws/signal?role=viewer   each dashboard video panel

Server -> camera : {"type":"viewer","id":V}   make an offer for viewer V
                   {"type":"bye","id":V}      viewer V left
Server -> viewer : {"type":"camera-on"} / {"type":"camera-off"}
Relayed          : offer / answer / ice. The camera sends {"to":V,...}; a
                   viewer's messages go to the camera with {"from":V,...}.
Media flows peer-to-peer on the LAN; the server never touches video."""
from __future__ import annotations

import itertools
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class Signaling:
    def __init__(self) -> None:
        self.camera: WebSocket | None = None
        self.viewers: dict[str, WebSocket] = {}
        self._ids = itertools.count(1)

    @staticmethod
    async def _send(ws: WebSocket | None, msg: dict) -> None:
        if ws is not None:
            try:
                await ws.send_text(json.dumps(msg))
            except Exception:
                pass

    def mount(self, app: FastAPI) -> None:
        @app.websocket("/ws/signal")
        async def signal(ws: WebSocket, role: str = "viewer"):
            await ws.accept()
            if role == "camera":
                await self._camera(ws)
            else:
                await self._viewer(ws)

    async def _camera(self, ws: WebSocket) -> None:
        if self.camera is not None:                 # a new phone replaces the old one
            old, self.camera = self.camera, None
            try:
                await old.close()
            except Exception:
                pass
        self.camera = ws
        for vid, v in list(self.viewers.items()):
            await self._send(v, {"type": "camera-on"})
            await self._send(ws, {"type": "viewer", "id": vid})
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                v = self.viewers.get(str(msg.pop("to", "")))
                await self._send(v, {**msg, "from": "camera"})
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            if self.camera is ws:
                self.camera = None
                for v in list(self.viewers.values()):
                    await self._send(v, {"type": "camera-off"})

    async def _viewer(self, ws: WebSocket) -> None:
        vid = str(next(self._ids))
        self.viewers[vid] = ws
        await self._send(ws, {"type": "camera-on" if self.camera else "camera-off"})
        await self._send(self.camera, {"type": "viewer", "id": vid})
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                msg.pop("to", None)
                await self._send(self.camera, {**msg, "from": vid})
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            self.viewers.pop(vid, None)
            await self._send(self.camera, {"type": "bye", "id": vid})
