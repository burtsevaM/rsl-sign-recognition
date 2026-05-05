"""Runtime-facing datatypes for BIO segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BioSegment:
    """Inclusive global-frame BIO segment boundary."""

    start: int
    end: int
    score: float

    def __post_init__(self) -> None:
        start = int(self.start)
        end = int(self.end)
        if end < start:
            raise ValueError(f"segment end must be >= start, got [{start}, {end}]")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "score", float(self.score))

    @property
    def length(self) -> int:
        return int(self.end - self.start + 1)

    def to_dict(self) -> dict[str, int | float]:
        return {
            "start": int(self.start),
            "end": int(self.end),
            "score": float(self.score),
        }

    def to_jsonable(self) -> dict[str, int | float]:
        return self.to_dict()


@dataclass(slots=True)
class StreamingBioResult:
    """Result returned after one streaming segmentation update."""

    ran_inference: bool
    sign_segments: list[BioSegment] = field(default_factory=list)
    phrase_segments: list[BioSegment] = field(default_factory=list)
    recent_sign_segments: list[BioSegment] = field(default_factory=list)
    recent_phrase_segments: list[BioSegment] = field(default_factory=list)
    active_sign: bool = False
    active_phrase: bool = False
    active_sign_progress: float = 0.0
    active_phrase_progress: float = 0.0
    latency_ms: float | None = None
    decode_latency_ms: float | None = None
    buffer_len: int = 0
    buffer_start: int = 0
    buffer_end: int = -1
    index_mode: str = "global"

    def to_dict(self) -> dict[str, object]:
        return {
            "ran_inference": bool(self.ran_inference),
            "sign_segments": [segment.to_jsonable() for segment in self.sign_segments],
            "phrase_segments": [
                segment.to_jsonable() for segment in self.phrase_segments
            ],
            "recent_sign_segments": [
                segment.to_jsonable() for segment in self.recent_sign_segments
            ],
            "recent_phrase_segments": [
                segment.to_jsonable() for segment in self.recent_phrase_segments
            ],
            "active_sign": bool(self.active_sign),
            "active_phrase": bool(self.active_phrase),
            "active_sign_progress": float(self.active_sign_progress),
            "active_phrase_progress": float(self.active_phrase_progress),
            "latency_ms": None if self.latency_ms is None else float(self.latency_ms),
            "decode_latency_ms": None
            if self.decode_latency_ms is None
            else float(self.decode_latency_ms),
            "buffer_len": int(self.buffer_len),
            "buffer_start": int(self.buffer_start),
            "buffer_end": int(self.buffer_end),
            "index_mode": str(self.index_mode),
        }

    def to_jsonable(self) -> dict[str, object]:
        return self.to_dict()


__all__ = ["BioSegment", "StreamingBioResult"]
