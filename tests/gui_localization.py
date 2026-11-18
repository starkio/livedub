"""Run with python tests/gui_localization.py. Uses Qt's offscreen platform."""

import os
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QGroupBox, QTabWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from livedub import config, gui  # noqa: E402
from livedub.audio.devices import SYSTEM_SOURCE  # noqa: E402
from livedub.config import (  # noqa: E402
    ENGINE_CASCADE,
    ENGINE_GEMINI,
    ENGINE_OPENAI_FILTERED,
    ENGINE_REALTIME,
    OPENAI_FILTERED_TEXT_MODELS,
    Settings,
)


def main():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication([])
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        with (
            patch.object(config, "CONFIG_DIR", directory),
            patch.object(config, "CONFIG_FILE", directory / "settings.json"),
            patch.object(gui, "IS_WINDOWS", False),
            patch.object(gui, "list_sources", return_value=[SYSTEM_SOURCE]),
            patch.object(gui, "list_outputs", return_value=[]),
            patch.object(gui, "default_output", return_value=None),
            patch.dict(os.environ, {"DEEPGRAM_API_KEY": ""}),
        ):
            config.CONFIG_FILE.write_text('{"target_lang": "ru"}', encoding="utf-8")
            assert Settings.load().ui_language == "tr"
            Settings(engine=ENGINE_REALTIME, source_device=SYSTEM_SOURCE.id, target_lang="ru").save()
            window = gui.MainWindow()
            assert window.settings_btn.text() == "Ayarlar…"
            assert window.src_lang.findData("az") == -1
            assert window.tgt_lang.findData("az") >= 0
            filtered_index = window.engine_combo.findData(ENGINE_OPENAI_FILTERED)
            assert not window.engine_combo.model().item(filtered_index).isEnabled()
            window._select(window.src_lang, "en")
            assert window.engine_combo.currentData() == ENGINE_OPENAI_FILTERED
            assert not window.engine_combo.isEnabled()
            window.source_view.line("Bağlanıyor…")
            window.target_view.line("Привет")

            expected_titles = {"ru": "Настройки", "en": "Settings", "tr": "Ayarlar"}
            defaults = Settings()
            model_preset = next(model for model in OPENAI_FILTERED_TEXT_MODELS
                                if model != defaults.openai_filtered_text_model)
            custom_model = "custom-translation-model"
            for language in ("ru", "en", "tr"):
                previous_language = window.settings.ui_language
                previous_model = window.settings.openai_filtered_text_model

                def select_locale(dialog):
                    assert dialog.windowTitle() == expected_titles[previous_language]
                    picker = dialog.findChild(QTabWidget).widget(0).findChild(QComboBox)
                    assert [picker.itemData(index) for index in range(picker.count())] == ["tr", "en", "ru"]
                    picker.setCurrentIndex(picker.findData(language))
                    tts = next(combo for combo in dialog.findChildren(QComboBox)
                               if combo.findData("elevenlabs_live") >= 0)
                    assert tts.findData("elevenlabs") >= 0 and tts.findData("openai") >= 0
                    assert tts.findData("windows_live") == -1
                    assert tts.currentData() == ("openai" if language == "ru" else "elevenlabs_live")
                    tts.setCurrentIndex(tts.findData("elevenlabs_live"))
                    filtered_title = dialog._(gui.ENGINE_LABELS[ENGINE_OPENAI_FILTERED])
                    filtered_group = next(group for group in dialog.findChildren(QGroupBox)
                                          if group.title() == filtered_title)
                    model = filtered_group.findChild(QComboBox)
                    assert model.isEditable() and model.currentText() == previous_model
                    assert tuple(model.itemText(i) for i in range(model.count())) == OPENAI_FILTERED_TEXT_MODELS
                    if language == "ru":
                        model.setCurrentIndex(model.findText(model_preset))
                    elif language == "en":
                        model.setEditText(custom_model)
                    return QDialog.DialogCode.Accepted

                with patch.object(gui.SettingsDialog, "exec", select_locale):
                    window._open_settings()
                app.processEvents()
                persisted = Settings.load()
                assert persisted.ui_language == language
                assert persisted.source_lang == "en" and persisted.target_lang == "ru"
                assert persisted.engine == ENGINE_REALTIME
                assert persisted.openai_filtered_text_model == (model_preset if language == "ru" else custom_model)
                assert persisted.translate_text_model == defaults.translate_text_model
                assert persisted.tts_provider == "elevenlabs_live" and persisted.elevenlabs_model == "eleven_flash_v2_5"
                assert window.source_view.toPlainText() == "Bağlanıyor…"
                assert window.target_view.toPlainText() == "Привет"
                assert window.settings_btn.text() == expected_titles[language] + "…"
                assert window.engine_combo.currentData() == ENGINE_OPENAI_FILTERED and not window.engine_combo.isEnabled()
                if language == "ru":
                    assert "Достаточно одного ключа OpenAI" in window.hint.text()
                    assert "всем исходным звуком" in window.hint.text()
                    window._on_event("status", {"text": "Bağlandı: OpenAI gpt-transcribe"})
                    assert window.state_label.text() == "Подключено: OpenAI gpt-transcribe"
                    window._on_event("latency", {"ms": 500})
                    assert window.latency_label.text() == "Задержка: 500 ms"

            window._select(window.src_lang, "auto")
            assert window.engine_combo.isEnabled() and window.engine_combo.currentData() == ENGINE_REALTIME
            window._select(window.engine_combo, ENGINE_CASCADE)
            window._select(window.src_lang, "en")
            assert window.engine_combo.currentData() == ENGINE_OPENAI_FILTERED
            with (
                patch.object(gui.SettingsDialog, "exec", return_value=QDialog.DialogCode.Accepted),
                patch.object(gui.SettingsDialog, "result_settings",
                             return_value=replace(window.settings, source_lang="en", deepgram_api_key="test-key")),
            ):
                window._open_settings()
            assert window.engine_combo.currentData() == ENGINE_CASCADE
            assert Settings.load().engine == ENGINE_CASCADE
            window.close()

            Settings(source_lang="az").save()
            legacy = gui.MainWindow()
            assert legacy.src_lang.currentData() == "az" and not legacy.start_btn.isEnabled()
            legacy._select(legacy.src_lang, "auto")
            assert legacy.start_btn.isEnabled()
            legacy.close()

            Settings(ui_language="ru", engine=ENGINE_GEMINI, target_lang="ru", source_device=SYSTEM_SOURCE.id).save()
            automatic = gui.MainWindow()
            assert "Gemini пропускает речь на языке перевода" in automatic.hint.text()
            assert "всем исходным звуком" in automatic.hint.text()
            automatic.close()

            with patch.object(gui, "IS_WINDOWS", True):
                localized_windows_labels = {
                    "tr": "Windows Live (ücretsiz, çevrimdışı)",
                    "en": "Windows Live (free, offline)",
                    "ru": "Windows Live (бесплатно, офлайн)",
                }
                for language, label in localized_windows_labels.items():
                    dialog = gui.SettingsDialog(Settings(ui_language=language))
                    tts = next(combo for combo in dialog.findChildren(QComboBox)
                               if combo.findData("windows_live") >= 0)
                    assert tts.currentData() == "openai"
                    index = tts.findData("windows_live")
                    assert tts.itemText(index) == label
                    tts.setCurrentIndex(index)
                    selected = dialog.result_settings()
                    selected.save()
                    assert Settings.load().tts_provider == "windows_live"
                    dialog.close()
    print("GUI localization and source-language selection passed")


if __name__ == "__main__":
    main()
