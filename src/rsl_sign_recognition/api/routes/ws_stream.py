"""WebSocket transport endpoint for contract v1."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from rsl_sign_recognition.api.ws_stream_runtime import WsStreamRuntimeSession

router = APIRouter()


@router.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime_session = WsStreamRuntimeSession.create(websocket.app.state.runtime_shell)

    try:
        while True:
            try:
                packet = await websocket.receive()
            except WebSocketDisconnect:
                break

            if packet["type"] == "websocket.disconnect":
                break

            if packet.get("text") is not None:
                await websocket.send_json(runtime_session.handle_text(packet["text"]))
                continue

            frame_bytes = packet.get("bytes")
            if frame_bytes is not None:
                await websocket.send_json(runtime_session.handle_binary(frame_bytes))
    finally:
        runtime_session.close()
