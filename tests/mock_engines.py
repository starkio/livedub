"""Offline protocol test: runs every engine against local mock servers (no API keys, no audio devices).

    python tests/mock_engines.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import numpy as np
from websockets.asyncio.server import serve

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from livedub.audio.util import f32_to_pcm16  # noqa: E402
from livedub.config import ENGINE_CASCADE, ENGINE_GEMINI, ENGINE_OPENAI_FILTERED, Settings  # noqa: E402
from livedub.engines import ENGINES, cascade, effective_engine, gemini_translate, openai_realtime, openai_stt, openai_translate  # noqa: E402

PORT = 8765
TONE = (np.sin(np.arange(4800) / 24000 * 2 * np.pi * 440) * 8000).astype("<i2").tobytes()  # 200 ms @ 24 kHz


class FakePlayer:
    backlog = 0.0
    speaking = False

    def __init__(self):
        self.samples = 0
        self.first_audio = asyncio.Event()

    def play(self, x, rate):
        assert rate == 24000
        self.samples += len(x)
        self.first_audio.set()
        return 0.0


# -- mock servers -------------------------------------------------------------------------------
async def translate_server(ws, log):
    appends = 0
    async for raw in ws:
        ev = json.loads(raw)
        log.append(ev["type"])
        if ev["type"] == "session.input_audio_buffer.append":
            appends += 1
            if appends % 10 == 0:
                await ws.send(json.dumps({"type": "session.input_transcript.delta", "delta": "hello "}))
                await ws.send(json.dumps({"type": "session.output_transcript.delta", "delta": "hola "}))
                await ws.send(json.dumps({"type": "session.output_audio.delta", "delta": base64.b64encode(TONE).decode()}))


async def gemini_server(ws, log):
    setup = json.loads(await ws.recv())["setup"]
    log.append(("setup", setup))
    await ws.send(json.dumps({"setupComplete": {}}).encode())  # Gemini uses binary frames
    chunks = 0
    async for raw in ws:
        audio = json.loads(raw)["realtimeInput"]["audio"]
        log.append(("audio", audio["mimeType"], len(base64.b64decode(audio["data"]))))
        chunks += 1
        if chunks % 5 == 0:
            content = {
                "inputTranscription": {"text": "hello "},
                "outputTranscription": {"text": "merhaba "},
                "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(TONE).decode()}}]},
            }
            await ws.send(json.dumps({"serverContent": content}).encode())
        if chunks == 12:
            await ws.send(json.dumps({"serverContent": {"turnComplete": True}}).encode())
            await ws.send(json.dumps({"goAway": {"timeLeft": "1s"}}).encode())


async def realtime_server(ws, log):
    appends = 0
    n = 0
    async for raw in ws:
        ev = json.loads(raw)
        log.append(ev["type"])
        if ev["type"] == "input_audio_buffer.append":
            appends += 1
            if appends % 8 == 0:  # one short utterance every 8 appends
                n += 1
                await ws.send(json.dumps({"type": "input_audio_buffer.speech_started"}))
                await ws.send(json.dumps({"type": "input_audio_buffer.speech_stopped"}))
                await ws.send(json.dumps({"type": "input_audio_buffer.committed", "item_id": f"u{n}"}))
                await ws.send(json.dumps({"type": "conversation.item.added", "item": {"id": f"u{n}"}}))
                await ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed", "transcript": f"sentence {n}"}))
        elif ev["type"] == "response.create":
            n += 1
            await ws.send(json.dumps({"type": "response.created", "response": {"id": f"r{n}"}}))
            await ws.send(json.dumps({"type": "conversation.item.added", "item": {"id": f"a{n}"}}))
            await ws.send(json.dumps({"type": "response.output_audio_transcript.delta", "delta": "cümle "}))
            await ws.send(json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(TONE).decode()}))
            await ws.send(json.dumps({"type": "response.output_audio_transcript.done"}))
            await ws.send(json.dumps({"type": "response.done", "response": {"status": "completed"}}))
        elif ev["type"] == "conversation.item.delete":
            await ws.send(json.dumps({"type": "conversation.item.deleted", "item_id": ev["item_id"]}))


async def deepgram_server(ws, log):
    params = parse_qs(urlsplit(ws.request.path).query)
    log.append(params)
    filtered = params.get("smart_format") != ["true"]
    chunks = 0
    async for raw in ws:
        log.append("binary" if isinstance(raw, bytes) else json.loads(raw).get("type"))
        chunks += 1
        if chunks % 12 == 0:
            if filtered:
                seconds = chunks * 0.02
                mixed = [
                    {"word": "watch", "punctuated_word": "Watch", "language": "en-US", "end": seconds - 0.18},
                    {"word": "out", "punctuated_word": "out!", "language": "en", "end": seconds - 0.13},
                    {"word": "погоди", "language": "ru", "end": seconds - 0.10},
                    {"word": "untagged", "end": seconds - 0.08},
                    {"word": "go", "punctuated_word": "Go.", "language": "en-GB", "end": seconds - 0.04},
                ]
                def result(words, final):
                    return {"type": "Results", "is_final": final, "speech_final": False, "channel": {
                        "alternatives": [{"transcript": "mixed and untrusted", "languages": ["ru", "en"], "words": words}]
                    }}

                await ws.send(json.dumps(result([{"word": "provisional", "language": "en"}], False)))
                await ws.send(json.dumps(result(mixed, True)))
                await ws.send(json.dumps(result([{"word": "привет", "language": "ru"}], True)))
                continue
            base = {"type": "Results", "channel": {"alternatives": [{"transcript": "This is a test"}]}}
            await ws.send(json.dumps({**base, "is_final": False}))
            await ws.send(json.dumps({**base, "is_final": True, "speech_final": True}))


async def openai_transcription_server(ws, log):
    assert ws.request.headers["Authorization"] == "Bearer sk-test"
    setup = json.loads(await ws.recv())
    log.append(setup["session"]["audio"]["input"])
    await ws.send(json.dumps({"type": "session.updated", "session": setup["session"]}))
    packets = 0
    async for raw in ws:
        event = json.loads(raw)
        assert event["type"] == "input_audio_buffer.append"
        assert len(base64.b64decode(event["audio"])) == 24000 * openai_stt.SEND_MS // 1000 * 2
        packets += 1
        if packets != 12:
            continue
        for index, (text, codes) in enumerate([
            ("Русская реплика.", ["ru"]),
            ("We should go. Пойдём.", ["en", "ru"]),
            ("Unknown language.", None),
            ("Watch out.", ["en-GB"]),
        ]):
            item = f"item_{index}"
            await ws.send(json.dumps({"type": "input_audio_buffer.speech_stopped", "item_id": item, "audio_end_ms": 400}))
            complete = {"type": "conversation.item.input_audio_transcription.completed", "item_id": item, "transcript": text}
            if codes is not None:
                complete["languages"] = [{"code": code} for code in codes]
            await ws.send(json.dumps(complete))


async def elevenlabs_server(ws, log):
    assert ws.request.headers["xi-api-key"] == "el-test"
    log.append(("connect", parse_qs(urlsplit(ws.request.path).query)))
    async for raw in ws:
        msg = json.loads(raw)
        context = msg.get("context_id")
        if msg.get("close_context"):
            await ws.send(json.dumps({"contextId": context, "isFinal": True}))
        if (msg.get("text") or "").strip():
            log.append(("text", context))
            data = base64.b64encode(TONE).decode()
            await ws.send(json.dumps({"context_id": context, "audio": data, "is_final": False}))


def text_delta(value: str) -> bytes:
    return f"data: {json.dumps({'choices': [{'delta': {'content': value}}]})}\n\n".encode()


def http_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/chat/completions":
        body = json.loads(request.content)
        assert body["stream"] is True and body["messages"][-1]["role"] == "user"
        sse = b"".join(text_delta(t) for t in ["Bu bir ", "test. ", "İkinci cümle"])
        return httpx.Response(200, content=sse + b"data: [DONE]\n\n")
    if request.url.path == "/v1/audio/speech":
        assert json.loads(request.content)["response_format"] == "pcm"
        return httpx.Response(200, content=TONE + b"\x01")  # odd byte count on purpose
    return httpx.Response(404)


# -- harness ------------------------------------------------------------------------------------
async def feed(queue: asyncio.Queue, rate: int):
    block = (np.random.randn(rate // 50) * 0.05).astype(np.float32)
    loop = asyncio.get_running_loop()
    next_block = loop.time()
    while True:
        await queue.put(block)
        next_block += 0.02
        await asyncio.sleep(max(0, next_block - loop.time()))


async def run_engine(engine_cls, settings, seconds=3.0, player=None):
    events: list[tuple[str, dict]] = []
    player = player if player is not None else FakePlayer()
    engine = engine_cls(settings, player, lambda kind, **data: events.append((kind, data)))
    queue: asyncio.Queue = asyncio.Queue()
    feeder = asyncio.create_task(feed(queue, engine.input_rate))
    task = asyncio.create_task(engine.run(queue))
    await asyncio.sleep(seconds)
    if task.done():
        task.result()
    task.cancel()
    feeder.cancel()
    await asyncio.gather(task, feeder, return_exceptions=True)
    return events, player


async def realtime_translation_frames() -> bool:
    frame_samples = 4800
    blocks = [
        np.full(470, 0.2, dtype=np.float32),
        np.zeros(940, dtype=np.float32),
        np.full(8300, -0.3, dtype=np.float32),
        np.linspace(-0.5, 0.5, 4800, dtype=np.float32),
    ]
    audio = asyncio.Queue()
    for block in blocks:
        audio.put_nowait(block)
    frames = []
    ready = asyncio.Event()

    class Socket:
        async def send(self, raw):
            frames.append(base64.b64decode(json.loads(raw)["audio"]))
            if len(frames) == 3:
                ready.set()

    engine = openai_translate.OpenAITranslateEngine(Settings(), FakePlayer(), lambda *args, **data: None)
    engine._onset = openai_translate.OnsetDetector()
    engine._latency = openai_translate.LatencyMeter(engine.emit)
    pump = asyncio.create_task(engine._pump(Socket(), audio))
    try:
        await asyncio.wait_for(ready.wait(), 1)
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
    expected = f32_to_pcm16(np.concatenate(blocks)[:3 * frame_samples])
    return all(len(frame) == frame_samples * 2 for frame in frames) and b"".join(frames) == expected


def kinds(events):
    return {k for k, _ in events}


async def main():
    logs: dict[str, list] = {
        "translate": [], "realtime": [], "deepgram": [], "gemini": [], "elevenlabs": [], "openai_stt": [],
    }

    async def router(ws):
        path = ws.request.path
        if path.startswith("/ws/google.ai.generativelanguage"):
            assert ws.request.headers["x-goog-api-key"] == "gm-test"
            await gemini_server(ws, logs["gemini"])
        elif path.startswith("/v1/realtime/translations"):
            await translate_server(ws, logs["translate"])
        elif path == "/v1/realtime?intent=transcription":
            await openai_transcription_server(ws, logs["openai_stt"])
        elif path.startswith("/v1/realtime"):
            assert ws.request.headers["Authorization"] == "Bearer sk-test"
            await realtime_server(ws, logs["realtime"])
        elif path.startswith("/v1/listen"):
            assert ws.request.headers["Authorization"] == "Token dg-test"
            await deepgram_server(ws, logs["deepgram"])
        elif path.startswith("/v1/text-to-speech/"):
            await elevenlabs_server(ws, logs["elevenlabs"])

    gemini_translate.URL = f"ws://127.0.0.1:{PORT}/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    openai_translate.URL = f"ws://127.0.0.1:{PORT}/v1/realtime/translations?model={{model}}"
    openai_realtime.URL = f"ws://127.0.0.1:{PORT}/v1/realtime?model={{model}}"
    openai_stt.URL = f"ws://127.0.0.1:{PORT}/v1/realtime?intent=transcription"
    deepgram_url = cascade.DeepgramSTT.url
    cascade.DeepgramSTT.url = lambda self: f"ws://127.0.0.1:{PORT}/v1/listen?{urlsplit(deepgram_url(self)).query}"
    elevenlabs_live_connect = cascade.elevenlabs_live_connect

    def local_elevenlabs(voice, key, model, language):
        real = elevenlabs_live_connect(voice, key, model, language)
        path = urlsplit(real.uri)
        return cascade.ws_connect(f"ws://127.0.0.1:{PORT}{path.path}?{path.query}", {"xi-api-key": key})

    cascade.elevenlabs_live_connect = local_elevenlabs
    real_client = httpx.AsyncClient
    translated_inputs = []
    translation_settings = {}
    live_player = None
    played_early = []

    class LiveTranslation(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield text_delta("Нам нужно быстро перебраться на другую сторону моста, пока вокруг всё ещё тихо и путь свободен ")
            if not played_early:
                try:
                    await asyncio.wait_for(live_player.first_audio.wait(), timeout=0.9)
                    played_early.append(True)
                except TimeoutError:
                    played_early.append(False)
            yield text_delta("и можно идти дальше.")
            yield b"data: [DONE]\n\n"

    def record_requests(request):
        if request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)
            translated_inputs.append(payload["messages"][-1]["content"])
            translation_settings.update(payload)
            if live_player is not None:
                return httpx.Response(200, stream=LiveTranslation())
        return http_handler(request)

    cascade.httpx.AsyncClient = lambda **kw: real_client(transport=httpx.MockTransport(record_requests), **kw)

    settings = Settings(openai_api_key="sk-test", deepgram_api_key="dg-test", target_lang="es")
    failures = []

    def check(name, cond):
        print(("  OK   " if cond else "  FAIL ") + name)
        if not cond:
            failures.append(name)

    async with serve(router, "127.0.0.1", PORT):
        print("gemini engine")
        ev, player = await run_engine(gemini_translate.GeminiTranslateEngine,
                                      Settings(gemini_api_key="gm-test", target_lang="tr"), seconds=4.0)
        setups = [e[1] for e in logs["gemini"] if e[0] == "setup"]
        audio = [e for e in logs["gemini"] if e[0] == "audio"]
        first = setups[0] if setups else {}
        check("setup: model + Turkish target", first.get("model") == "models/gemini-3.5-live-translate-preview"
              and first["generationConfig"]["translationConfig"] == {"targetLanguageCode": "tr", "echoTargetLanguage": False})
        check("setup: transcriptions at setup level", "outputAudioTranscription" in first and "inputAudioTranscription" in first)
        chunk_bytes = 16000 * gemini_translate.SEND_MS // 1000 * 2
        check(f"audio 16 kHz in {gemini_translate.SEND_MS} ms chunks",
              audio and all(a[1] == "audio/pcm;rate=16000" and a[2] == chunk_bytes for a in audio))
        check("dub audio played", player.samples >= 4800 * 2)
        check("transcripts + latency emitted", {"source_delta", "target_delta", "target_end", "latency"} <= kinds(ev))
        check("reconnected after goAway", len(setups) >= 2)
        check("no errors", "error" not in kinds(ev))

        print("translate engine")
        ev, player = await run_engine(openai_translate.OpenAITranslateEngine, settings)
        check("session.update sent first", logs["translate"][:1] == ["session.update"])
        check("audio appended", logs["translate"].count("session.input_audio_buffer.append") >= 10)
        check("dub audio played", player.samples >= 4800)
        check("transcripts + latency emitted", {"source_delta", "target_delta", "latency"} <= kinds(ev))
        check("exact 200 ms frames preserve sample order, leftovers and input silence",
              await realtime_translation_frames())

        playback = FakePlayer()
        timing = []
        translate_engine = openai_translate.OpenAITranslateEngine(
            settings, playback, lambda kind, **data: timing.append((kind, data))
        )
        translate_engine._latency = openai_translate.LatencyMeter(translate_engine.emit)
        translate_engine._latency.mark()
        translate_engine._output_active = False
        empty = b"\x00\x00" * 4800
        speech = b"\x00\x00" * 1200 + np.full(600, 1234, dtype="<i2").tobytes()
        def send_output(pcm):
            translate_engine._handle({
                "type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode(),
            })

        send_output(empty)
        check("digital output silence does not occupy the player or end the latency timer", playback.samples == 0 and not timing)
        send_output(speech)
        check("idle speech keeps 10 ms of lead-in and reports first audible latency",
              playback.samples == 840 and [kind for kind, _ in timing] == ["latency"])
        send_output(empty)
        send_output(empty)
        check("a silent run keeps only a short resampler tail after speech", playback.samples == 840 + 480)
        playback.backlog = 0.1
        send_output(speech)
        check("leading pause is preserved when voiced audio is already queued", playback.samples == 840 + 480 + 1800)

        print("realtime engine")
        ev, player = await run_engine(openai_realtime.OpenAIRealtimeEngine, settings, seconds=4.0)
        log = logs["realtime"]
        check("two session.updates (base + transcription)", log[:2] == ["session.update", "session.update"])
        check("responses requested", log.count("response.create") >= 3)
        check("old items pruned", log.count("conversation.item.delete") >= 1)
        check("dub audio played", player.samples >= 4800 * 3)
        check("source + target text", {"source_line", "target_delta", "target_end", "latency"} <= kinds(ev))
        check("no errors", "error" not in kinds(ev))

        print("cascade engine")
        ev, player = await run_engine(cascade.CascadeEngine, Settings(openai_api_key="sk-test", deepgram_api_key="dg-test", target_lang="tr"))
        check("pcm streamed to deepgram", logs["deepgram"].count("binary") > 20)
        check("segments translated", any(k == "target_delta" for k, _ in ev))
        check("tts audio played (odd byte handled)", player.samples >= 4800 * 2)
        check("latency reported at first PCM", "latency" in kinds(ev))
        check("no errors", "error" not in kinds(ev), )
        errors = [d for k, d in ev if k == "error"]
        if errors:
            print("   ", errors[:3])

        print("selected source language")
        selected = Settings(engine=ENGINE_CASCADE, source_lang="en", target_lang="ru",
                            openai_api_key="sk-test", deepgram_api_key="dg-test", deepgram_model="nova-2",
                            translate_text_model="gpt-6-luna")
        check("Auto preserves selected engine", effective_engine(Settings(engine=ENGINE_GEMINI)) == ENGINE_GEMINI)
        check("explicit Cascade with its configured key preserves Deepgram", effective_engine(selected) == ENGINE_CASCADE)
        translated_inputs.clear()
        logs["deepgram"].clear()
        ev, player = await run_engine(ENGINES[effective_engine(selected)], selected, seconds=1.3)
        params = next((p for p in logs["deepgram"] if isinstance(p, dict)), {})
        check("multilingual Nova-3, fast endpointing, no smart-format delay",
              params.get("model") == ["nova-3"] and params.get("language") == ["multi"]
              and params.get("endpointing") == ["150"] and "smart_format" not in params)
        check("only final en and en-region words are translated before speech_final",
              translated_inputs[:2] == ["Watch out!", "Go."] and set(translated_inputs) == {"Watch out!", "Go."})
        check("Luna streams translation with reasoning disabled",
              translation_settings.get("model") == "gpt-6-luna" and translation_settings.get("reasoning_effort") == "none")
        check("original transcript shows filtered spans",
              [data["text"] for kind, data in ev if kind == "source_line"] == translated_inputs)
        latency = [data["ms"] for kind, data in ev if kind == "latency"]
        check("filtered audio played and timed by segment",
              player.samples >= 4800 * 4 and len(latency) >= 2 and all(ms >= 0 for ms in latency))
        if latency:
            print(f"   Mock: estimated delay from word end to first audio {min(latency)}–{max(latency)} ms")

        print("ElevenLabs Live TTS")
        live_player = FakePlayer()
        live_settings = replace(selected, tts_provider="elevenlabs_live", elevenlabs_api_key="el-test")
        ev, player = await run_engine(cascade.CascadeEngine, live_settings, seconds=1.6, player=live_player)
        connections = [data for kind, data in logs["elevenlabs"] if kind == "connect"]
        contexts = {context for kind, context in logs["elevenlabs"] if kind == "text"}
        check("audio starts while translation is still streaming", played_early == [True])
        check("one WebSocket reused for multiple phrases, native PCM",
              len(connections) == 1 and connections[0].get("output_format") == ["pcm_24000"] and len(contexts) >= 2)
        check("live audio reaches playback with latency events", player.samples >= len(TONE) // 2 and "latency" in kinds(ev))
        check("no unexpected live errors", "error" not in kinds(ev))

        print("Windows Live TTS")
        live_player = FakePlayer()
        played_early.clear()
        windows_calls = []

        @asynccontextmanager
        async def windows_voice(language):
            check("offline voice receives the target language", language == "ru")

            class Voice:
                async def speak(self, text, speed=1.0):
                    windows_calls.append(text)
                    return TONE

            yield Voice()

        cascade.windows_live_voice = windows_voice
        offline_settings = replace(selected, tts_provider="windows_live", elevenlabs_api_key="")
        ev, player = await run_engine(cascade.CascadeEngine, offline_settings, seconds=1.35, player=live_player)
        check("offline audio starts while translation is still streaming", played_early == [True])
        check("offline provider plays Russian text without another API", bool(windows_calls) and player.samples > 0
              and len([kind for kind, _ in logs["elevenlabs"] if kind == "connect"]) == len(connections))
        check("no offline provider errors", "error" not in kinds(ev) and "latency" in kinds(ev))

        print("selected language with one OpenAI key")
        single = Settings(engine=ENGINE_GEMINI, source_lang="en", target_lang="ru", openai_api_key="sk-test",
                          openai_filtered_text_model=" gpt-6.2-sol ")
        check("explicit EN with only an OpenAI key selects OpenAI", effective_engine(single) == ENGINE_OPENAI_FILTERED)
        live_player = None
        translated_inputs.clear()
        ev, player = await run_engine(ENGINES[effective_engine(single)], single, seconds=1.3)
        params = logs["openai_stt"][0] if logs["openai_stt"] else {}
        check("STT identifies the actual language and uses short pauses",
              params.get("transcription") == {"model": "gpt-transcribe"}
              and params.get("turn_detection", {}).get("silence_duration_ms") == 100)
        check("only confirmed English goes to translation and captions",
              translated_inputs == ["Watch out."]
              and [data["text"] for kind, data in ev if kind == "source_line"] == ["Watch out."])
        check("configured model reaches the selected-source translator with compatible reasoning",
              translation_settings.get("model") == "gpt-6.2-sol" and translation_settings.get("reasoning_effort") == "low")
        check("dubbing and latency work with no Deepgram or ElevenLabs key",
              player.samples > 0 and "latency" in kinds(ev) and "error" not in kinds(ev))

    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
