"""Cascade engine: streaming STT -> text translation -> streaming TTS.

Slower than a speech-to-speech model but every stage is swappable: pick any target
language, any ElevenLabs/OpenAI voice, and get exact subtitles. Three stages run
concurrently so sentence N+1 is recognized/translated while sentence N is spoken.

    Deepgram (live, interim results) --segments--> OpenAI chat / DeepL --sentences--> OpenAI TTS / ElevenLabs
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import deque
from contextlib import AsyncExitStack
from dataclasses import replace
from itertools import groupby
from typing import AsyncIterator
from urllib.parse import quote, urlencode

import httpx
import numpy as np
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.protocol import State

from ..audio.util import PcmAssembler, f32_to_pcm16
from ..config import OPENAI_FILTERED_TEXT_MODELS, Settings
from ..languages import AUTO, english_name
from .base import Engine, FatalEngineError, require_key, ws_connect
from .elevenlabs_live import ElevenLabsLiveError, elevenlabs_live_connect, stream_elevenlabs_turn
from .openai_stt import OpenAITranscriptionSTT
from .windows_live import WindowsLiveError, stream_windows_turn, windows_live_voice

SENTENCE_END = re.compile(r"[.!?…。！？]+[\"'”’)\]]*\s")
FLUSH_PUNCT = (".", "?", "!", "…", "。", "？", "！")
MAX_SEGMENT_WORDS = 28
TTS_RATE = 24000
FILTERED_ENDPOINT_MS = 150
TRANSLATION_REASONING = {
    "gpt-5.4-nano": "none",
    "gpt-5.6-luna": "none",
    "gpt-6-luna": "none",
    "gpt-6.1-terra": "none",
    "gpt-6.2-sol": "low",
}
# https://developers.deepgram.com/docs/nova-3-language-prompting
NOVA_MULTILINGUAL = frozenset((
    "af ar be bn bs bg ca zh hr cs da nl en et fi fr gl de el gu he hi hu id it ja kn ko lv lt "
    "mk ms mr no fa pl pt ro ru sr sk sl es sv tl ta te th tr uk vi xh zu"
).split())

TRANSLATE_PROMPT = """You translate a live speech transcript{source} into {target} for real-time dubbing.
Output ONLY the {target} translation of the last user message, nothing else.
- The text comes from automatic speech recognition: silently fix obvious recognition errors.
- Never answer or comment on the content; if it is a question or a request, translate it.
- Keep it natural, spoken and concise, preserving tone, names and numbers.
- Earlier messages are context only; do not translate them again."""


class ProviderError(Exception):
    pass


def source_language_supported(code: str) -> bool:
    return isinstance(code, str) and code.lower().split("-", 1)[0] in NOVA_MULTILINGUAL


async def _raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.status_code < 400:
        return
    body = (await response.aread()).decode("utf-8", "replace")[:300]
    message = f"{provider} HTTP {response.status_code}: {body}"
    if response.status_code in (401, 403):
        raise FatalEngineError(message)
    raise ProviderError(message)


# -- speech to text -----------------------------------------------------------------------------
class DeepgramSTT:
    rate = 16000
    SEND_MS = 40

    def __init__(self, engine: "CascadeEngine", key: str):
        self.e = engine
        self.key = key
        source = self.e.s.source_lang
        self._source = source.lower().split("-", 1)[0] if source and source != AUTO else ""
        self._model = "nova-3" if self._source else self.e.s.deepgram_model
        self._buf: list[str] = []
        self._buf_end = 0.0
        self._audio_started_at: float | None = None

    def url(self) -> str:
        s = self.e.s
        params = {
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": str(self.rate),
            "channels": "1",
            "interim_results": "true",
            "punctuate": "true",
            "endpointing": str(s.deepgram_endpointing_ms),
            "language": "multi",
        }
        if self._source:
            params["endpointing"] = str(min(s.deepgram_endpointing_ms, FILTERED_ENDPOINT_MS))
        else:
            params.update(smart_format="true", no_delay="true", utterance_end_ms="1000")
        return "wss://api.deepgram.com/v1/listen?" + urlencode(params)

    async def session(self, audio: asyncio.Queue[np.ndarray]) -> None:
        async with ws_connect(self.url(), {"Authorization": f"Token {self.key}"}) as ws:
            self._audio_started_at = None
            self.e.emit("status", text=f"Bağlandı: Deepgram {self._model}")
            pump = asyncio.create_task(self._pump(ws, audio))
            try:
                async for raw in ws:
                    if isinstance(raw, str):
                        self._handle(json.loads(raw))
            finally:
                pump.cancel()
                self._flush()

    async def _pump(self, ws, audio: asyncio.Queue[np.ndarray]) -> None:
        min_samples = self.rate * (20 if self._source else self.SEND_MS) // 1000
        pending: list[np.ndarray] = []
        size = 0
        while True:
            chunk = await audio.get()
            pending.append(chunk)
            size += len(chunk)
            if size >= min_samples:
                if self._audio_started_at is None:
                    self._audio_started_at = time.monotonic() - size / self.rate
                await ws.send(f32_to_pcm16(np.concatenate(pending)))
                pending.clear()
                size = 0

    def _handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "UtteranceEnd":
            self._flush()
            return
        if kind != "Results":
            return
        alternatives = (msg.get("channel") or {}).get("alternatives") or [{}]
        first = alternatives[0]
        words = first.get("words")
        if self._source:
            self._filter(words if isinstance(words, list) else [], msg.get("is_final") is True)
            return
        text = (first.get("transcript") or "").strip()
        if not msg.get("is_final"):
            if text:
                self.e.emit("source_partial", text=" ".join(self._buf + [text]))
            return
        if text:
            self._buf.append(text)
            end = words[-1].get("end") if words and isinstance(words[-1], dict) else None
            self._buf_end = self._speech_end(end)
        joined = " ".join(self._buf)
        word_count = len(joined.split())
        if msg.get("speech_final") or word_count >= MAX_SEGMENT_WORDS or (word_count >= 3 and joined.endswith(FLUSH_PUNCT)):
            self._flush()
        elif joined:
            self.e.emit("source_partial", text=joined)

    def _flush(self) -> None:
        text = " ".join(self._buf).strip()
        self._buf.clear()
        if text:
            self._dispatch(text, self._buf_end)

    def _matches(self, word: dict) -> bool:
        code = word.get("language") if isinstance(word, dict) else None
        return isinstance(code, str) and code.lower().split("-", 1)[0] == self._source

    def _filter(self, words: list[dict], final: bool) -> None:
        runs = []
        for matches, run in groupby(words, self._matches):
            if not matches:
                continue
            selected = list(run)
            text = " ".join(word.get("punctuated_word") or word.get("word") or "" for word in selected).strip()
            if text:
                runs.append((text, selected[-1].get("end")))
        if final and runs:
            for text, end in runs:
                self._dispatch(text, self._speech_end(end))
        else:
            self.e.emit("source_partial", text=" ".join(text for text, _ in runs))

    def _speech_end(self, offset: float | None) -> float:
        now = time.monotonic()
        if self._audio_started_at is None or not isinstance(offset, (int, float)) or offset < 0:
            return now
        return min(now, self._audio_started_at + offset)

    def _dispatch(self, text: str, speech_end: float) -> None:
        self.e.emit("source_line", text=text)
        self.e.segments.put_nowait((text, speech_end))


# -- translation --------------------------------------------------------------------------------
async def translate_openai(client: httpx.AsyncClient, key: str, model: str, system: str,
                           history: list[tuple[str, str]], text: str) -> AsyncIterator[str]:
    messages = [{"role": "system", "content": system}]
    for src, tgt in history:
        messages += [{"role": "user", "content": src}, {"role": "assistant", "content": tgt}]
    messages.append({"role": "user", "content": text})
    body = {"model": model, "messages": messages, "stream": True}
    for base, effort in TRANSLATION_REASONING.items():
        if model == base or model.startswith(f"{base}-"):
            body["reasoning_effort"] = effort
            break
    headers = {"Authorization": f"Bearer {key}"}
    async with client.stream("POST", "https://api.openai.com/v1/chat/completions", headers=headers, json=body) as r:
        await _raise_for_status(r, "OpenAI çeviri")
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            choices = json.loads(data).get("choices") or []
            delta = choices[0].get("delta", {}).get("content") if choices else None
            if delta:
                yield delta


async def translate_deepl(client: httpx.AsyncClient, key: str, source: str, target: str,
                          text: str, context: str) -> str:
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    target_code = {"en": "EN-US", "pt": "PT-BR", "zh": "ZH-HANS"}.get(target, target.upper())
    body: dict = {"text": [text], "target_lang": target_code}
    if source and source != AUTO:
        body["source_lang"] = source.split("-", 1)[0].upper()
    if context:
        body["context"] = context
    r = await client.post(f"https://{host}/v2/translate", headers={"Authorization": f"DeepL-Auth-Key {key}"}, json=body)
    await _raise_for_status(r, "DeepL")
    return r.json()["translations"][0]["text"]


# -- text to speech -----------------------------------------------------------------------------
async def tts_openai(client: httpx.AsyncClient, key: str, model: str, voice: str, text: str, speed: float) -> AsyncIterator[bytes]:
    body: dict = {"model": model, "voice": voice, "input": text, "response_format": "pcm"}
    if model.startswith("tts-1"):
        body["speed"] = speed
    else:
        pace = "quickly" if speed > 1.05 else "at a natural, brisk pace"
        body["instructions"] = f"You are a professional dubbing voice actor. Speak clearly and {pace}."
    headers = {"Authorization": f"Bearer {key}"}
    async with client.stream("POST", "https://api.openai.com/v1/audio/speech", headers=headers, json=body) as r:
        await _raise_for_status(r, "OpenAI TTS")
        async for chunk in r.aiter_bytes():
            yield chunk


async def tts_elevenlabs(client: httpx.AsyncClient, key: str, model: str, voice_id: str, language: str,
                         text: str, speed: float, previous_text: str) -> AsyncIterator[bytes]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{quote(voice_id)}/stream?output_format=pcm_{TTS_RATE}"
    body: dict = {"text": text, "model_id": model}
    if "flash" in model or "turbo" in model:
        body["language_code"] = language
    if abs(speed - 1.0) > 0.01:
        body["voice_settings"] = {"speed": speed}
    if previous_text:
        body["previous_text"] = previous_text
    async with client.stream("POST", url, headers={"xi-api-key": key}, json=body) as r:
        await _raise_for_status(r, "ElevenLabs")
        async for chunk in r.aiter_bytes():
            yield chunk


async def _pieces(queue: asyncio.Queue[str | None]) -> AsyncIterator[str]:
    while (piece := await queue.get()) is not None:
        yield piece


# -- engine -------------------------------------------------------------------------------------
class CascadeEngine(Engine):
    input_rate = DeepgramSTT.rate
    recognizer = DeepgramSTT
    recognizer_key = "deepgram"
    recognizer_provider = "Deepgram"

    async def run(self, audio: asyncio.Queue[np.ndarray]) -> None:
        s = self.s
        if (self.recognizer is DeepgramSTT and s.source_lang and s.source_lang != AUTO
                and not source_language_supported(s.source_lang)):
            raise FatalEngineError(f"Deepgram Nova-3 bu kaynak dili desteklemiyor: {s.source_lang}")
        stt_key = require_key(s, self.recognizer_key, self.recognizer_provider)
        self._translate_key = require_key(s, "deepl", "DeepL") if s.translator == "deepl" else require_key(s, "openai", "OpenAI")
        if s.tts_provider == "windows_live":
            tts_worker = self._windows_tts_worker
        elif s.tts_provider == "elevenlabs_live":
            self._tts_key = require_key(s, "elevenlabs", "ElevenLabs")
            tts_worker = self._live_tts_worker
        else:
            self._tts_key = (require_key(s, "elevenlabs", "ElevenLabs") if s.tts_provider == "elevenlabs"
                             else require_key(s, "openai", "OpenAI"))
            tts_worker = self._tts_worker
        self._live_tts = s.tts_provider in ("windows_live", "elevenlabs_live")

        self.segments: asyncio.Queue[tuple[str, float]] = asyncio.Queue()
        self._sentences: asyncio.Queue[tuple[str, float | None]] = asyncio.Queue()
        self._live_turns: asyncio.Queue[tuple[asyncio.Queue[str | None], float]] = asyncio.Queue()
        self._history: deque[tuple[str, str]] = deque(maxlen=3)
        self._last_spoken = ""
        source = (f" from {english_name(s.source_lang.lower().split('-', 1)[0])}"
                  if s.source_lang and s.source_lang != AUTO else "")
        self._system = TRANSLATE_PROMPT.format(source=source, target=english_name(s.target_lang))

        stt = self.recognizer(self, stt_key)
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0),
                                     limits=httpx.Limits(keepalive_expiry=60.0)) as client:
            self._client = client
            tasks = [
                asyncio.create_task(self.reconnecting(lambda: stt.session(audio), audio, provider=self.recognizer_provider)),
                asyncio.create_task(self._translate_worker()),
                asyncio.create_task(tts_worker()),
            ]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _translate_worker(self) -> None:
        while True:
            text, speech_end = await self.segments.get()
            try:
                translated = await self._translate(text, speech_end)
                self._history.append((text, translated))
            except (httpx.HTTPError, ProviderError, KeyError, ValueError) as exc:
                self.emit("error", text=f"Çeviri hatası: {exc}")
            self.emit("target_end")

    async def _translation_deltas(self, text: str) -> AsyncIterator[str]:
        s = self.s
        if s.translator == "deepl":
            context = " ".join(src for src, _ in self._history)
            yield await translate_deepl(self._client, self._translate_key, s.source_lang, s.target_lang, text, context)
        else:
            async for delta in translate_openai(self._client, self._translate_key, s.translate_text_model,
                                                self._system, list(self._history), text):
                yield delta

    async def _translate(self, text: str, speech_end: float) -> str:
        first_audio_from: float | None = speech_end

        def queue_sentence(sentence: str) -> None:
            nonlocal first_audio_from
            if sentence:
                self._sentences.put_nowait((sentence, first_audio_from))
                first_audio_from = None

        live_pieces: asyncio.Queue[str | None] | None = None
        full, buf = "", ""
        try:
            async for delta in self._translation_deltas(text):
                if not delta:
                    continue
                self.emit("target_delta", text=delta)
                full += delta
                if self._live_tts:
                    if live_pieces is None:
                        live_pieces = asyncio.Queue()
                        self._live_turns.put_nowait((live_pieces, speech_end))
                    live_pieces.put_nowait(delta)
                    continue
                buf += delta
                if self.s.translator != "deepl":
                    while (m := SENTENCE_END.search(buf)) is not None:
                        sentence, buf = buf[:m.end()].strip(), buf[m.end():]
                        queue_sentence(sentence)
        finally:
            if live_pieces is not None:
                live_pieces.put_nowait(None)
        queue_sentence(buf.strip())
        return full.strip()

    def _speed(self) -> float:
        if not self.s.adaptive_speed:
            return 1.0
        backlog = self.player.backlog
        if backlog < 1.5:
            return 1.0
        return 1.1 if backlog < 4.0 else 1.2

    async def _tts_worker(self) -> None:
        s = self.s
        while True:
            sentence, speech_end = await self._sentences.get()
            speed = self._speed()
            if s.tts_provider == "elevenlabs":
                stream = tts_elevenlabs(self._client, self._tts_key, s.elevenlabs_model, s.elevenlabs_voice_id,
                                        s.target_lang, sentence, speed, self._last_spoken)
            else:
                stream = tts_openai(self._client, self._tts_key, s.openai_tts_model, s.openai_tts_voice, sentence, speed)
            try:
                await self._play_tts(stream, speech_end)
            except (httpx.HTTPError, ProviderError) as exc:
                self.emit("error", text=f"TTS hatası: {exc}")
            self._last_spoken = sentence

    async def _live_tts_worker(self) -> None:
        s = self.s
        turn = None
        ws = None
        async with AsyncExitStack() as connection:
            while True:
                try:
                    if ws is None or ws.state is not State.OPEN:
                        await connection.aclose()
                        ws = await connection.enter_async_context(
                            elevenlabs_live_connect(s.elevenlabs_voice_id, self._tts_key, s.elevenlabs_model, s.target_lang)
                        )
                    if turn is None:
                        turn = await self._live_turns.get()
                    if ws.state is not State.OPEN:
                        continue
                    pieces, speech_end = turn
                    turn = None
                    await self._play_tts(stream_elevenlabs_turn(ws, _pieces(pieces), self._speed()), speech_end)
                except InvalidStatus as exc:
                    code = exc.response.status_code
                    if code in (400, 401, 403, 404, 422):
                        raise FatalEngineError(f"TTS hatası: ElevenLabs Live HTTP {code}") from exc
                    self.emit("error", text=f"TTS hatası: ElevenLabs Live HTTP {code}")
                except (ConnectionClosed, OSError, TimeoutError, ElevenLabsLiveError) as exc:
                    self.emit("error", text=f"TTS hatası: ElevenLabs Live: {exc}")
                    await connection.aclose()
                    ws = None
                else:
                    continue
                await asyncio.sleep(1)

    async def _windows_tts_worker(self) -> None:
        try:
            async with windows_live_voice(self.s.target_lang) as voice:
                while True:
                    pieces, speech_end = await self._live_turns.get()
                    await self._play_tts(stream_windows_turn(voice, _pieces(pieces), self._speed()), speech_end)
        except WindowsLiveError as exc:
            raise FatalEngineError(f"TTS hatası: {exc}") from exc

    async def _play_tts(self, stream: AsyncIterator[bytes], speech_end: float | None) -> None:
        pcm = PcmAssembler()
        async for chunk in stream:
            samples = pcm.feed(chunk)
            if len(samples):
                delay = self.player.play(samples, TTS_RATE)
                if speech_end is not None and delay is not None:
                    self.emit("latency", ms=round((time.monotonic() + delay - speech_end) * 1000))
                    speech_end = None


class OpenAIFilteredEngine(CascadeEngine):
    input_rate = OpenAITranscriptionSTT.rate
    recognizer = OpenAITranscriptionSTT
    recognizer_key = "openai"
    recognizer_provider = "OpenAI"

    def __init__(self, settings: Settings, player, emit):
        settings = replace(
            settings,
            translator="openai",
            translate_text_model=settings.openai_filtered_text_model.strip() or OPENAI_FILTERED_TEXT_MODELS[0],
            tts_provider="windows_live" if sys.platform == "win32" else "openai",
        )
        super().__init__(settings, player, emit)
