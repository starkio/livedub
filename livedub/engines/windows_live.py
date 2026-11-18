"""Offline speech synthesis with a prewarmed Windows desktop voice."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import struct
import subprocess
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

import numpy as np


_MAX_FRAME = 24_000 * 2 * 120
_REQUEST_TIMEOUT = 10
_CHUNK_LENGTH = 64
_LEADING_SILENCE = 32
_PREROLL_SAMPLES = 600  # Keep 25 ms of the quiet onset at 24 kHz.
_CLAUSE_END = re.compile(r'[.!?…;:。！？][»”"’)]*(?=\s|$)')

# Windows PowerShell ships with System.Speech. Text is data sent through stdin.
_WORKER = """
$ErrorActionPreference = 'Stop'
$encoding = [Text.UTF8Encoding]::new($false, $true)
$reader = [IO.StreamReader]::new([Console]::OpenStandardInput(), $encoding)
$writer = [IO.BinaryWriter]::new([Console]::OpenStandardOutput())

function Send-Frame([byte[]]$data, [bool]$failed = $false) {
    $size = [int]$data.Length
    if ($failed) { $size = -$size }
    $writer.Write($size)
    $writer.Write($data)
    $writer.Flush()
}

function Invoke-Synthesis([string]$text, [int]$rate) {
    $buffer = [IO.MemoryStream]::new()
    try {
        $synth.Rate = $rate
        $synth.SetOutputToAudioStream($buffer, $format)
        $synth.Speak($text)
        return ,$buffer.ToArray()
    } finally {
        $synth.SetOutputToNull()
        $buffer.Dispose()
    }
}

try {
    $locale = (ConvertFrom-Json -InputObject $reader.ReadLine()).language
    Add-Type -AssemblyName System.Speech
    $synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $installed = $synth.GetInstalledVoices() | Where-Object { $_.Enabled }
    $selected = $installed | Where-Object { $_.VoiceInfo.Culture.Name -eq $locale } | Select-Object -First 1
    if (-not $selected) {
        $language = $locale.Split('-')[0]
        $selected = $installed | Where-Object { $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $language } |
            Select-Object -First 1
    }
    if (-not $selected) { throw "No enabled Windows desktop voice for $locale." }
    $name = $selected.VoiceInfo.Name
    $synth.SelectVoice($name)
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $null = Invoke-Synthesis '1' 0
    Send-Frame ($encoding.GetBytes($name))

    while ($null -ne ($line = $reader.ReadLine())) {
        $request = ConvertFrom-Json -InputObject $line
        Send-Frame (Invoke-Synthesis $request.text $request.rate)
    }
} catch {
    Send-Frame ($encoding.GetBytes($_.Exception.Message)) $true
} finally {
    if ($synth) { $synth.Dispose() }
    $writer.Dispose()
    $reader.Dispose()
}
"""
_ENCODED_WORKER = base64.b64encode(_WORKER.encode("utf-16-le")).decode("ascii")


class WindowsLiveError(RuntimeError):
    """The selected Windows desktop voice could not produce audio."""


class _Voice:
    def __init__(self, process: asyncio.subprocess.Process):
        self._process = process
        self.name = ""

    async def _exchange(self, request: dict) -> bytes:
        stdin = self._process.stdin
        stdout = self._process.stdout
        stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
        await stdin.drain()
        size = struct.unpack("<i", await stdout.readexactly(4))[0]
        if abs(size) > _MAX_FRAME:
            raise WindowsLiveError("Invalid Windows speech response size.")
        data = await stdout.readexactly(abs(size))
        if size < 0:
            raise WindowsLiveError(data.decode("utf-8", errors="replace"))
        return data

    async def request(self, request: dict) -> bytes:
        try:
            return await asyncio.wait_for(self._exchange(request), timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise WindowsLiveError("Windows speech timed out.") from exc
        except (OSError, asyncio.IncompleteReadError) as exc:
            raise WindowsLiveError("Windows speech process closed unexpectedly.") from exc

    async def speak(self, text: str, speed: float = 1.0) -> bytes:
        if not any(character.isalnum() for character in text):
            return b""
        rate = max(-10, min(10, round((speed - 1.0) * 10)))
        pcm = await self.request({"text": text, "rate": rate})
        if not pcm or len(pcm) % 2:
            raise WindowsLiveError("Windows speech returned invalid PCM audio.")
        samples = np.frombuffer(pcm, dtype="<i2")
        initial_signal = int(((samples > _LEADING_SILENCE) | (samples < -_LEADING_SILENCE)).argmax())
        return pcm[max(0, initial_signal - _PREROLL_SAMPLES) * 2:]


@asynccontextmanager
async def windows_live_voice(language: str) -> AsyncIterator[_Voice]:
    """Start and warm a local voice matching the requested language (e.g. ru)."""
    if sys.platform != "win32":
        raise WindowsLiveError("Windows speech is available only on Windows.")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        process = await asyncio.create_subprocess_exec(
            str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
            "-WindowStyle", "Hidden", "-EncodedCommand", _ENCODED_WORKER,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, NotImplementedError) as exc:
        raise WindowsLiveError("Could not start Windows speech.") from exc

    voice = _Voice(process)
    try:
        voice.name = (await voice.request({"language": language})).decode("utf-8", errors="replace")
        if not voice.name:
            raise WindowsLiveError("Windows speech did not select a voice.")
        yield voice
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.communicate(), timeout=1.0)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.communicate()


async def stream_windows_turn(
    voice: _Voice, pieces: AsyncIterator[str], speed: float,
) -> AsyncIterator[bytes]:
    """Synthesize complete short clauses while the rest of the text arrives."""
    buffer = ""
    async for piece in pieces:
        buffer += piece
        while buffer:
            match = _CLAUSE_END.search(buffer)
            end = match.end() if match else 0
            if len(buffer) > _CHUNK_LENGTH and (not end or end > _CHUNK_LENGTH):
                boundary = max(buffer.rfind(" ", 0, _CHUNK_LENGTH + 1), buffer.rfind("\n", 0, _CHUNK_LENGTH + 1))
                if boundary > 0:
                    end = boundary
            if not end:
                break
            phrase, buffer = buffer[:end].strip(), buffer[end:].lstrip()
            if phrase:
                yield await voice.speak(phrase, speed)
    if phrase := buffer.strip():
        yield await voice.speak(phrase, speed)
