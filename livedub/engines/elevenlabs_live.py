"""Bidirectional ElevenLabs text-to-speech on a reusable WebSocket."""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import suppress
from typing import AsyncIterator
from urllib.parse import quote, urlencode
from uuid import uuid4

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException

from .base import ws_connect

RESPONSE_TIMEOUT_S = 30


class ElevenLabsLiveError(RuntimeError):
    """A synthesis error or unexpected response from the ElevenLabs WebSocket."""


def elevenlabs_live_connect(voice_id: str, key: str, model: str, language: str):
    params = {"model_id": model, "output_format": "pcm_24000", "inactivity_timeout": 180}
    if language and ("flash" in model or "turbo" in model):
        params["language_code"] = language.split("-", 1)[0]
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{quote(voice_id, safe='')}/multi-stream-input"
    return ws_connect(f"{url}?{urlencode(params)}", {"xi-api-key": key})


async def stream_elevenlabs_turn(
    ws: ClientConnection, pieces: AsyncIterator[str], speed: float
) -> AsyncIterator[bytes]:
    """Play back 24 kHz PCM as complete words arrive, then close just this context."""
    context_id = uuid4().hex
    initialized = False
    closing = False

    async def send(**message) -> None:
        await ws.send(json.dumps({"context_id": context_id, **message}))

    async def send_text() -> bool:
        nonlocal initialized, closing
        await send(text=" ", voice_settings={"speed": speed},
                   generation_config={"chunk_length_schedule": [50, 80, 120, 120]})
        initialized = True
        partial_word = ""
        has_text = False
        async for piece in pieces:
            if not piece:
                continue
            text = partial_word + piece
            words = text.split()
            # SSE splits inside words. ElevenLabs expects a trailing space per message.
            partial_word = "" if text[-1].isspace() else words.pop()
            if words:
                await send(text=" ".join(words) + " ")
                has_text = True
        if partial_word:
            await send(text=partial_word + " ")
            has_text = True
        if has_text:
            await send(flush=True)
        closing = True
        await send(close_context=True)
        return has_text

    sender = asyncio.create_task(send_text())
    receiver: asyncio.Task | None = None
    try:
        while True:
            receiver = asyncio.create_task(ws.recv())
            if not sender.done():
                done, _ = await asyncio.wait((sender, receiver), timeout=RESPONSE_TIMEOUT_S,
                                             return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise ElevenLabsLiveError("ElevenLabs WebSocket response timed out")
            if sender.done() and not sender.result():
                return
            try:
                raw = await asyncio.wait_for(receiver, RESPONSE_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                raise ElevenLabsLiveError("ElevenLabs WebSocket response timed out") from exc
            try:
                event = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise ElevenLabsLiveError("Invalid ElevenLabs WebSocket response") from exc
            if not isinstance(event, dict):
                raise ElevenLabsLiveError("Invalid ElevenLabs WebSocket response")

            response_context = event.get("contextId") or event.get("context_id")
            if response_context and response_context != context_id:
                continue
            if event.get("error") or event.get("message") or event.get("detail"):
                raise ElevenLabsLiveError("ElevenLabs rejected WebSocket synthesis")
            if response_context != context_id:
                continue
            if encoded := event.get("audio"):
                try:
                    audio = base64.b64decode(encoded, validate=True)
                except (TypeError, ValueError) as exc:
                    raise ElevenLabsLiveError("Invalid ElevenLabs audio chunk") from exc
                yield audio
            if event.get("isFinal") is True or event.get("is_final") is True:
                if not closing:
                    raise ElevenLabsLiveError("ElevenLabs closed the context before text was complete")
                await sender
                return
    finally:
        tasks = [sender] if receiver is None else [sender, receiver]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if initialized and not closing:
            with suppress(OSError, WebSocketException, asyncio.TimeoutError):
                await asyncio.wait_for(send(close_context=True), 0.5)
