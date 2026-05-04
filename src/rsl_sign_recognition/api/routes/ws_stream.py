"""WebSocket transport endpoint for contract v1."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from rsl_sign_recognition.contracts.websocket_v1 import (
    frame_decode_failed_error,
    is_jpeg_packet,
    response_for_client_text,
    runtime_unavailable_error,
)

router = APIRouter()


@router.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    while True:
        try:
            packet = await websocket.receive()
        except WebSocketDisconnect:
            break

        if packet["type"] == "websocket.disconnect":
            break

        if packet.get("text") is not None:
            await websocket.send_json(response_for_client_text(packet["text"]))
            continue

        frame_bytes = packet.get("bytes")
        if frame_bytes is not None:
            if not is_jpeg_packet(frame_bytes):
                await websocket.send_json(frame_decode_failed_error())
                continue

            await websocket.send_json(runtime_unavailable_error())
