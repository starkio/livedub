from ..config import ENGINE_CASCADE, ENGINE_GEMINI, ENGINE_OPENAI_FILTERED, ENGINE_REALTIME, ENGINE_TRANSLATE, Settings
from ..languages import AUTO
from .base import Engine, FatalEngineError
from .cascade import CascadeEngine, OpenAIFilteredEngine, source_language_supported
from .gemini_translate import GeminiTranslateEngine
from .openai_realtime import OpenAIRealtimeEngine
from .openai_translate import OpenAITranslateEngine

ENGINES: dict[str, type[Engine]] = {
    ENGINE_GEMINI: GeminiTranslateEngine,
    ENGINE_TRANSLATE: OpenAITranslateEngine,
    ENGINE_REALTIME: OpenAIRealtimeEngine,
    ENGINE_CASCADE: CascadeEngine,
    ENGINE_OPENAI_FILTERED: OpenAIFilteredEngine,
}

ENGINE_LABELS = {
    ENGINE_GEMINI: "Gemini Live Translate — eşzamanlı, Türkçe dahil 70+ dil (en ucuz)",
    ENGINE_TRANSLATE: "OpenAI Realtime Translate — eşzamanlı (13 çıkış dili, Türkçe yok)",
    ENGINE_REALTIME: "OpenAI Realtime GPT — tercüman modu, tüm diller",
    ENGINE_CASCADE: "Kaskad: Deepgram → çeviri → TTS (ElevenLabs/OpenAI ses)",
    ENGINE_OPENAI_FILTERED: "OpenAI — seçili kaynak dili, tek anahtar",
}


def effective_engine(settings: Settings) -> str:
    if settings.source_lang and settings.source_lang != AUTO:
        if settings.engine == ENGINE_CASCADE and settings.key("deepgram"):
            return ENGINE_CASCADE
        return ENGINE_OPENAI_FILTERED
    return settings.engine


__all__ = ["ENGINES", "ENGINE_LABELS", "Engine", "FatalEngineError", "effective_engine", "source_language_supported"]
