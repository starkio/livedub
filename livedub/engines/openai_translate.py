"""OpenAI gpt-realtime-translate: continuous simultaneous interpretation.

The model listens to a never-ending audio stream and speaks the translation while
the speaker is still talking, so there is no turn taking to manage. Input language
is auto-detected; output is limited to TRANSLATE_MODEL_OUTPUTS.
"""

from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import quote

import numpy as np

from ..audio.util import f32_to_pcm16, pcm16_to_f32
from ..languages import TRANSLATE_MODEL_OUTPUTS, display_name
from .base import Engine, LatencyMeter, OnsetDetector, error_text, require_key, ws_connect

URL = "wss://api.openai.com/v1/realtime/translations?model={model}"
SEND_MS = 200  # The translation endpoint buffers input until a full 200 ms frame is available.
AUDIBLE_THRESHOLD = 10 ** (-45 / 20)


class OpenAITranslateEngine(Engine):
    input_rate = 24000

    async def run(self, audio: asyncio.Queue[np.ndarray]) -> None:
        self._key = require_key(self.s, "openai", "OpenAI")
        if self.s.target_lang not in TRANSLATE_MODEL_OUTPUTS:
            self.emit(
                "error",
                text=f"{display_name(self.s.target_lang)} bu modelin desteklediği çıkış dilleri arasında değil; "
                "sonuç alamazsanız 'OpenAI Realtime' motorunu seçin.",
            )
        await self.reconnecting(lambda: self._session(audio), audio)

    def _session_config(self, with_transcription: bool) -> dict:
        audio_cfg: dict = {"output": {"language": self.s.target_lang}}
        input_cfg: dict = {}
        if self.s.noise_reduction:
            input_cfg["noise_reduction"] = {"type": self.s.noise_reduction}
        if with_transcription:
            input_cfg["transcription"] = {"model": self.s.translate_transcribe_model}
        if input_cfg:
            audio_cfg["input"] = input_cfg
        return {"type": "session.update", "session": {"audio": audio_cfg}}

    async def _session(self, audio: asyncio.Queue[np.ndarray]) -> None:
        self._latency = LatencyMeter(self.emit)
        self._onset = OnsetDetector()
        self._output_active = False
        url = URL.format(model=quote(self.s.translate_model))
        async with ws_connect(url, {"Authorization": f"Bearer {self._key}"}) as ws:
            await ws.send(json.dumps(self._session_config(False)))
            if self.s.show_source_text and self.s.translate_transcribe_model:
                # Separate update: if the transcription model is rejected, translation keeps working.
                await ws.send(json.dumps(self._session_config(True)))
            self.emit("status", text=f"Bağlandı: {self.s.translate_model} → {display_name(self.s.target_lang)}")
            pump = asyncio.create_task(self._pump(ws, audio))
            try:
                async for raw in ws:
                    if self._handle(json.loads(raw)):
                        return
            finally:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    async def _pump(self, ws, audio: asyncio.Queue[np.ndarray]) -> None:
        frame_bytes = self.input_rate * SEND_MS // 1000 * 2
        pending = bytearray()
        while True:
            chunk = await audio.get()
            # Only time onsets that start while nothing is being dubbed; otherwise the reading
            # measures leftover audio of the previous sentence.
            if self._onset.feed(chunk) and not self.player.speaking:
                self._latency.mark()
            pending.extend(f32_to_pcm16(chunk))
            while len(pending) >= frame_bytes:
                payload = base64.b64encode(pending[:frame_bytes]).decode("ascii")
                del pending[:frame_bytes]
                await ws.send(json.dumps({"type": "session.input_audio_buffer.append", "audio": payload}))

    def _handle(self, ev: dict) -> bool:
        kind = ev.get("type", "")
        if kind == "session.output_audio.delta":
            samples = pcm16_to_f32(base64.b64decode(ev["delta"]))
            if not len(samples):
                return False
            nonzero = samples != 0
            if not nonzero.any():
                if self._output_active:
                    # The output resampler needs a short tail to emit the end of the preceding speech.
                    self.player.play(samples[:self.input_rate // 50], self.input_rate)
                    self._output_active = False
                return False
            self._output_active = True
            if not self.player.backlog:
                # The device already outputs silence when the queue is empty. Keep 10 ms before speech.
                pre_roll = self.input_rate // 100
                samples = samples[max(0, int(nonzero.argmax()) - pre_roll):]
            audible = np.flatnonzero(np.abs(samples) >= AUDIBLE_THRESHOLD)
            delay = self.player.play(samples, self.input_rate)
            if delay is not None and len(audible):
                self._latency.audio_arrived(delay + audible[0] / self.input_rate)
        elif kind == "session.output_transcript.delta":
            self.emit("target_delta", text=ev.get("delta", ""))
        elif kind == "session.input_transcript.delta":
            self.emit("source_delta", text=ev.get("delta", ""))
        elif kind.startswith("session.output_transcript.") and kind.endswith((".done", ".completed")):
            self.emit("target_end")
        elif kind.startswith("session.input_transcript.") and kind.endswith((".done", ".completed")):
            self.emit("source_end")
        elif kind == "error":
            self.emit("error", text=error_text(ev))
        elif kind == "session.closed":
            return True
        return False
