"""WebSocket frame decoding helpers for runtime-facing RGB input."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError

from rsl_sign_recognition.contracts.websocket_v1 import is_jpeg_packet


class FrameDecodeError(ValueError):
    """Raised when a binary WebSocket frame is not a decodable JPEG image."""


def decode_jpeg_rgb(frame_bytes: bytes) -> np.ndarray:
    """Decode a binary JPEG packet into the RGB uint8 frame expected by runtime."""

    if not isinstance(frame_bytes, bytes) or not is_jpeg_packet(frame_bytes):
        raise FrameDecodeError("binary frame is not a complete JPEG packet")

    try:
        with Image.open(BytesIO(frame_bytes)) as image:
            if image.format != "JPEG":
                raise FrameDecodeError("binary frame is not encoded as JPEG")
            rgb_image = image.convert("RGB")
            rgb_frame = np.asarray(rgb_image, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FrameDecodeError("binary frame could not be decoded as JPEG") from exc

    if rgb_frame.ndim != 3 or rgb_frame.shape[2] != 3:
        raise FrameDecodeError("decoded JPEG frame is not RGB")
    if rgb_frame.shape[0] < 1 or rgb_frame.shape[1] < 1:
        raise FrameDecodeError("decoded JPEG frame is empty")
    return np.ascontiguousarray(rgb_frame, dtype=np.uint8)


__all__ = ["FrameDecodeError", "decode_jpeg_rgb"]
