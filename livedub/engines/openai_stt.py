"""OpenAI Realtime transcription with a strict detected-language filter."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import TYPE_CHECKING

import numpy as np

from ..audio.util import f32_to_pcm16
from .base import FatalEngineError, error_text, ws_connect

if TYPE_CHECKING:
    from .cascade import CascadeEngine


URL = "wss://api.openai.com/v1/realtime?intent=transcription"
MODEL = "gpt-transcribe"
SEND_MS = 20
VAD_SILENCE_MS = 100
SETUP_TIMEOUT_S = 15


class OpenAITranscriptionSTT:
    rate = 24000
    input_rate = rate

    def __init__(self, engine: CascadeEngine, key: str):
        self.e = engine
        self.key = key
        self._source = engine.s.source_lang.strip().lower().split("-", 1)[0]
        self._audio_started_at: float | None = None
        self._speech_ends: dict[str, float] = {}

    def _setup(self) -> dict:
        audio_input = {
            "format": {"type": "audio/pcm", "rate": self.input_rate},
            "transcription": {"model": MODEL},
            "turn_detection": {
                "type": "server_vad",
                "threshold": self.e.s.vad_threshold,
                "prefix_padding_ms": 200,
                "silence_duration_ms": VAD_SILENCE_MS,
            },
        }
        if self.e.s.noise_reduction:
            audio_input["noise_reduction"] = {"type": self.e.s.noise_reduction}
        return {"type": "session.update", "session": {
            "type": "transcription", "audio": {"input": audio_input},
        }}

    async def session(self, audio: asyncio.Queue[np.ndarray]) -> None:
        self._audio_started_at = None
        self._speech_ends.clear()
        async with ws_connect(URL, {"Authorization": f"Bearer {self.key}"}) as ws:
            await ws.send(json.dumps(self._setup()))
            await asyncio.wait_for(self._wait_for_setup(ws), SETUP_TIMEOUT_S)
            self.e.emit("status", text=f"Bağlandı: OpenAI {MODEL}")

            sender = asyncio.create_task(self._pump(ws, audio))
            receiver = asyncio.create_task(self._receive(ws))
            tasks = (sender, receiver)
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _wait_for_setup(self, ws) -> None:
        while True:
            ev = json.loads(await ws.recv())
            kind = ev.get("type")
            if kind == "error":
                raise FatalEngineError(f"OpenAI: {error_text(ev)}")
            if kind in {"session.updated", "transcription_session.updated"}:
                return

    async def _pump(self, ws, audio: asyncio.Queue[np.ndarray]) -> None:
        min_samples = self.input_rate * SEND_MS // 1000
        pending: list[np.ndarray] = []
        size = 0
        while True:
            chunk = await audio.get()
            pending.append(chunk)
            size += len(chunk)
            if size < min_samples:
                continue
            if self._audio_started_at is None:
                self._audio_started_at = time.monotonic() - size / self.input_rate
            payload = base64.b64encode(f32_to_pcm16(np.concatenate(pending))).decode("ascii")
            await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": payload}))
            pending.clear()
            size = 0

    async def _receive(self, ws) -> None:
        async for raw in ws:
            self._handle(json.loads(raw))

    def _handle(self, ev: dict) -> None:
        kind = ev.get("type")
        item_id = ev.get("item_id")
        if kind == "error":
            raise FatalEngineError(f"OpenAI: {error_text(ev)}")
        if kind == "conversation.item.input_audio_transcription.failed":
            if isinstance(item_id, str):
                self._speech_ends.pop(item_id, None)
            self.e.emit("error", text=f"OpenAI: {error_text(ev)}")
            return
        if not isinstance(item_id, str):
            return
        if kind == "input_audio_buffer.speech_stopped":
            now = time.monotonic()
            offset_ms = ev.get("audio_end_ms")
            if self._audio_started_at is not None and type(offset_ms) is int and offset_ms >= 0:
                # OpenAI includes the configured VAD silence in its stop offset.
                now = min(now, self._audio_started_at + max(0, offset_ms - VAD_SILENCE_MS) / 1000)
            if len(self._speech_ends) >= 64:
                self._speech_ends.pop(next(iter(self._speech_ends)))
            self._speech_ends[item_id] = now
        elif kind == "conversation.item.input_audio_transcription.completed":
            speech_end = self._speech_ends.pop(item_id, time.monotonic())
            text = ev.get("transcript")
            if isinstance(text, str) and text.strip() and self._matches(ev.get("languages")):
                text = text.strip()
                self.e.emit("source_line", text=text)
                self.e.segments.put_nowait((text, speech_end))

    def _matches(self, languages: object) -> bool:
        if not self._source or not isinstance(languages, list) or not languages:
            return False
        for language in languages:
            code = language.get("code") if isinstance(language, dict) else None
            if not isinstance(code, str) or code.strip().lower().split("-", 1)[0] != self._source:
                return False
        return True
