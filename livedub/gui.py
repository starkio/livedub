"""PySide6 desktop UI."""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio.devices import IS_MAC, IS_WINDOWS, SYSTEM_LOOPBACK_ID, Device, default_output, list_outputs, list_sources
from .config import (
    CONFIG_FILE,
    ENGINE_CASCADE,
    ENGINE_GEMINI,
    ENGINE_OPENAI_FILTERED,
    ENGINE_TRANSLATE,
    OPENAI_FILTERED_TEXT_MODELS,
    Settings,
)
from .engines import ENGINE_LABELS, effective_engine, source_language_supported
from .i18n import UI_LANGUAGES, translate, translate_message
from .languages import AUTO, LANGUAGES, TRANSLATE_MODEL_OUTPUTS, display_name
from .session import SWITCH_NOTE, DubSession, plan_input


def _fit_combo(combo: QComboBox, minimum_chars: int) -> None:
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(minimum_chars)
    combo.currentTextChanged.connect(combo.setToolTip)


def _add_option(combo: QComboBox, label: str, value) -> None:
    combo.addItem(label, value)
    combo.setItemData(combo.count() - 1, label, Qt.ItemDataRole.ToolTipRole)


class Bridge(QObject):
    """Carries session events (emitted on worker threads) to the Qt main thread."""

    event = Signal(str, object)


class LiveText(QPlainTextEdit):
    """Append-only transcript view that understands streaming deltas and interim text."""

    GAP_S = 1.5

    def __init__(self, placeholder: str):
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(400)
        self.setPlaceholderText(placeholder)
        font = self.font()
        font.setPointSize(font.pointSize() + 2)
        self.setFont(font)
        self._open = False
        self._last = 0.0
        self._partial = 0

    def _insert(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _drop_partial(self) -> None:
        if self._partial:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, self._partial)
            cursor.removeSelectedText()
            self._partial = 0

    def _new_paragraph(self) -> None:
        if not self.document().isEmpty():
            self._insert("\n")

    def delta(self, text: str) -> None:
        self._drop_partial()
        now = time.monotonic()
        if self._open and now - self._last > self.GAP_S:
            self._open = False
        if not self._open:
            text = text.lstrip()
            if not text:
                return
            self._new_paragraph()
            self._open = True
        self._insert(text)
        self._last = now

    def end(self) -> None:
        self._open = False

    def partial(self, text: str) -> None:
        self._drop_partial()
        self._open = False
        chunk = ("\n" if not self.document().isEmpty() else "") + text
        self._insert(chunk)
        self._partial = len(chunk.encode("utf-16-le")) // 2  # Qt cursor positions count UTF-16 units

    def line(self, text: str) -> None:
        self._drop_partial()
        self._open = False
        self._new_paragraph()
        self._insert(text)


# -- settings dialog ----------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._ = partial(translate, settings.ui_language)
        self.setWindowTitle(self._("Ayarlar"))
        self.setMinimumWidth(560)
        self._settings = settings
        self._getters: dict[str, callable] = {}

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), self._("Genel"))
        tabs.addTab(self._keys_tab(), self._("API anahtarları"))
        tabs.addTab(self._gemini_tab(), "Gemini")
        tabs.addTab(self._openai_tab(), self._("OpenAI motorları"))
        tabs.addTab(self._cascade_tab(), self._("Kaskad motoru"))
        tabs.addTab(self._advanced_tab(), self._("Gelişmiş"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self._("Tamam"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self._("İptal"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # widget factories bound to a Settings attribute
    def _text(self, attr: str, secret: bool = False) -> QLineEdit:
        w = QLineEdit(str(getattr(self._settings, attr)))
        if secret:
            w.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self._getters[attr] = lambda: w.text().strip()
        return w

    def _editable(self, attr: str, options: Sequence[str]) -> QComboBox:
        w = QComboBox()
        w.setEditable(True)
        w.addItems(options)
        w.setCurrentText(str(getattr(self._settings, attr)))
        self._getters[attr] = lambda: w.currentText().strip()
        return w

    def _choice(self, attr: str, options: Sequence[tuple[str, str]]) -> QComboBox:
        w = QComboBox()
        _fit_combo(w, 16)
        for value, label in options:
            _add_option(w, label, value)
        index = w.findData(getattr(self._settings, attr))
        w.setCurrentIndex(max(index, 0))
        self._getters[attr] = lambda: w.currentData()
        return w

    def _check(self, attr: str, label: str) -> QCheckBox:
        w = QCheckBox(label)
        w.setChecked(bool(getattr(self._settings, attr)))
        self._getters[attr] = w.isChecked
        return w

    def _int(self, attr: str, lo: int, hi: int, step: int, suffix: str = "") -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setSuffix(suffix)
        w.setValue(int(getattr(self._settings, attr)))
        self._getters[attr] = w.value
        return w

    def _float(self, attr: str, lo: float, hi: float, step: float, suffix: str = "", scale: float = 1.0) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(2)
        w.setSuffix(suffix)
        w.setValue(float(getattr(self._settings, attr)) * scale)
        self._getters[attr] = lambda: w.value() / scale
        return w

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: gray;")
        return label

    def _general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(self._("Arayüz dili"), self._choice("ui_language", UI_LANGUAGES))
        return page

    def _keys_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Gemini", self._text("gemini_api_key", secret=True))
        link_text = self._("Ücretsiz Gemini anahtarı al (Google AI Studio)")
        link = QLabel(f'<a href="https://aistudio.google.com/apikey">{link_text}</a>')
        link.setOpenExternalLinks(True)
        form.addRow("", link)
        form.addRow("OpenAI", self._text("openai_api_key", secret=True))
        form.addRow("Deepgram", self._text("deepgram_api_key", secret=True))
        form.addRow("ElevenLabs", self._text("elevenlabs_api_key", secret=True))
        form.addRow("DeepL", self._text("deepl_api_key", secret=True))
        form.addRow(self._note(self._(
            "Anahtarlar düz metin olarak {path} dosyasında saklanır. Boş bırakılırsa ortam değişkenleri "
            "(GEMINI_API_KEY, OPENAI_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, DEEPL_API_KEY) kullanılır.\n"
            "Gemini motoru için bir Gemini anahtarı yeterlidir. Seçili kaynak diliyle çalışan OpenAI motoru dahil tüm "
            "OpenAI motorları yalnızca OpenAI anahtarı ister. Kaskad için Deepgram ve seçili çeviri sağlayıcısının "
            "anahtarları gerekir. Windows Live seslendirme için ayrı anahtar gerekmez.",
            path=CONFIG_FILE,
        )))
        return page

    def _gemini_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(self._("Live Translate modeli"), self._editable("gemini_translate_model", ["gemini-3.5-live-translate-preview"]))
        form.addRow(self._note(
            self._("Konuşmacı konuşurken çevirir; kaynak dili kendisi algılar, ses tonu konuşmacıya uyarlanır. "
            "Dublaj sesi yakalanan kaynağa geri karışırsa model kendi sesini tekrar çevirip döngüye girer; bu yüzden "
            "sistem sesi için 'Tüm sistem sesi (dublaj hariç)' kaynağını kullanın.\n"
            "Ücret: ücretsiz katmanda ses girişi bedava, çeviri sesi dakikada yaklaşık 0,018 $. Ücretsiz katmanda "
            "gönderilen içerik Google tarafından ürün geliştirmede kullanılabilir.")
        ))
        return page

    def _openai_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        common = QGroupBox(self._("Ortak"))
        form = QFormLayout(common)
        form.addRow(self._("Gürültü azaltma"), self._choice("noise_reduction", [
            ("", self._("Kapalı (sistem sesi için önerilir)")),
            ("near_field", self._("Yakın mikrofon / kulaklık mikrofonu")),
            ("far_field", self._("Uzak mikrofon / oda")),
        ]))
        layout.addWidget(common)

        filtered = QGroupBox(self._(ENGINE_LABELS[ENGINE_OPENAI_FILTERED]))
        form = QFormLayout(filtered)
        form.addRow(self._("Metin çeviri modeli"),
                    self._editable("openai_filtered_text_model", OPENAI_FILTERED_TEXT_MODELS))
        form.addRow(self._note(self._("OpenAI bu modeli seçili kaynak dili modunda metin çevirisi için kullanır.")))
        layout.addWidget(filtered)

        translate = QGroupBox(self._("Realtime Translate (eşzamanlı çeviri)"))
        form = QFormLayout(translate)
        form.addRow(self._("Model"), self._editable("translate_model", ["gpt-realtime-translate"]))
        form.addRow(self._("Kaynak transkript modeli"), self._editable("translate_transcribe_model", ["gpt-realtime-whisper"]))
        form.addRow(self._note(self._("Ses tonu konuşmacıya göre otomatik uyarlanır; ses seçimi yoktur. Çıkış dilleri: ")
                               + ", ".join(sorted(TRANSLATE_MODEL_OUTPUTS))))
        layout.addWidget(translate)

        realtime = QGroupBox(self._("Realtime GPT (tercüman modu)"))
        form = QFormLayout(realtime)
        form.addRow(self._("Model"), self._editable("realtime_model", ["gpt-realtime-1.5", "gpt-realtime-2", "gpt-realtime-2.1", "gpt-realtime", "gpt-realtime-mini"]))
        form.addRow(self._("Ses seçimi"), self._editable("realtime_voice", ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]))
        form.addRow(self._("Konuşma hızı"), self._float("realtime_speed", 0.25, 1.5, 0.05, "x"))
        form.addRow(self._("Akıl yürütme"), self._choice("realtime_reasoning", [
            ("", self._("Model varsayılanı")), ("minimal", self._("minimal (en hızlı)")), ("low", "low"),
        ]))
        form.addRow(self._("Kaynak transkript modeli"), self._editable("realtime_transcribe_model", ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"]))
        form.addRow(self._("Cümle sonu algılama"), self._choice("vad_type", [
            ("server_vad", self._("Sessizliğe göre (server_vad) — en hızlı")),
            ("semantic_vad", self._("Anlama göre (semantic_vad) — daha doğal ama yavaş")),
        ]))
        form.addRow(self._("Sessizlik eşiği"), self._int("vad_silence_ms", 150, 1500, 50, " ms"))
        form.addRow(self._("VAD hassasiyeti"), self._float("vad_threshold", 0.1, 0.95, 0.05))
        form.addRow(self._("En uzun parça"), self._float("max_turn_s", 3.0, 20.0, 0.5, self._(" sn")))
        form.addRow(self._note(self._("Akıl yürütme ayarı yalnızca gpt-realtime-2 ailesinde geçerlidir. 'En uzun parça': "
                               "konuşmacı hiç durmasa bile bu sürede bir çeviri tetiklenir.")))
        layout.addWidget(realtime)
        layout.addStretch()
        return page

    def _cascade_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(self._("Deepgram modeli"), self._editable("deepgram_model", ["nova-3", "nova-2"]))
        form.addRow(self._("Cümle sonu (endpointing)"), self._int("deepgram_endpointing_ms", 100, 2000, 50, " ms"))
        form.addRow(self._("Çevirmen"), self._choice("translator", [("openai", self._("OpenAI (bağlama duyarlı LLM)")), ("deepl", self._("DeepL (çok hızlı)"))]))
        form.addRow(self._("Çeviri modeli (OpenAI)"), self._editable("translate_text_model", [
            "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o-mini", "gpt-6-luna",
        ]))
        voices = [
            ("openai", "OpenAI TTS"),
            ("elevenlabs", "ElevenLabs (HTTP)"),
            ("elevenlabs_live", "ElevenLabs Live (WebSocket)"),
        ]
        if IS_WINDOWS:
            voices.append(("windows_live", self._("Windows Live (ücretsiz, çevrimdışı)")))
        form.addRow(self._("Seslendirme (TTS)"), self._choice("tts_provider", voices))
        form.addRow(self._("OpenAI TTS modeli"), self._editable("openai_tts_model", ["gpt-4o-mini-tts", "tts-1"]))
        form.addRow(self._("OpenAI TTS sesi"), self._editable("openai_tts_voice", ["coral", "marin", "cedar", "alloy", "ash", "ballad", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]))
        form.addRow(self._("ElevenLabs modeli"), self._editable("elevenlabs_model", ["eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_multilingual_v2"]))
        form.addRow(self._("ElevenLabs ses ID"), self._text("elevenlabs_voice_id"))
        form.addRow(self._note(self._(
            "ElevenLabs Live, çeviri sürerken metin alır. Flash/Turbo v2 ve v2.5 ile çalışır. "
            "Düşük gecikme için Flash v2.5 önerilir."
        )))
        if IS_WINDOWS:
            form.addRow(self._note(self._(
                "Windows Live, hedef dil için Windows'ta yüklü bir sesi kullanır. Seslendirme için API anahtarı gerekmez. "
                "OpenAI çevirisinde ses, çeviri tamamlanmadan başlayabilir."
            )))
        form.addRow(self._check("adaptive_speed", self._("Gecikme birikirse seslendirmeyi hızlandır")))
        form.addRow(self._note(self._("Deepgram anahtarı varken Kaskad seçilirse Nova-3, seçili kaynak dildeki kelimeleri filtreler.")))
        return page

    def _advanced_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(self._check("show_source_text", self._("Duyulan konuşmanın metnini göster (OpenAI'da ek transkripsiyon ücreti)")))
        form.addRow(self._("Geri besleme koruması"), self._choice("feedback_guard", [
            ("auto", self._("Otomatik (önerilir)")), ("on", self._("Her zaman açık")), ("off", self._("Kapalı")),
        ]))
        form.addRow(self._("Dublajda orijinali kıs"), self._float("duck_level", 0.0, 100.0, 5.0, " %", scale=100.0))
        form.addRow(self._note(
            self._("Geri besleme koruması: dublaj sesi yakalanan kaynağa geri sızabiliyorsa (aynı hoparlörün sistem sesi ya da "
            "hoparlörü duyan bir mikrofon), dublaj çalarken giriş susturulur. Bu sırada konuşulanlar kaçabilir; en iyi "
            "sonuç için kulaklık veya sanal kablo (VB-CABLE / BlackHole) kullanın. Otomatik modda, kaynak çıkışla aynı "
            "cihazın sistem sesiyse bunun yerine 'Tüm sistem sesi (dublaj hariç)' yakalanır ve giriş susturulmaz.\n"
            "'Dublajda orijinali kıs': orijinal sesi de çalıyorsanız, dublaj konuşurken orijinalin bu seviyeye inmesi.")
        ))
        return page

    def result_settings(self) -> Settings:
        return replace(self._settings, **{attr: get() for attr, get in self._getters.items()})


# -- main window --------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(980, 680)
        self.settings = Settings.load()
        self.session: DubSession | None = None
        self._sources: list[Device] = []
        self._outputs: list[Device] = []

        self.bridge = Bridge()
        self.bridge.event.connect(self._on_event)

        if IS_WINDOWS:
            try:
                from .audio.sessions import recover

                recover()  # apps left turned down by a run that did not shut down cleanly
            except Exception:
                pass
        self._build()
        self._refresh_devices()
        self._load_widgets()
        self._update_hints()

    # -- layout ---------------------------------------------------------------------------------
    def _build(self) -> None:
        self._ = partial(translate, self.settings.ui_language)
        self.setWindowTitle(f"LiveDub {__version__} — {self._('Canlı Çeviri ve Dublaj')}")
        root = QWidget()
        layout = QVBoxLayout(root)

        audio = QGroupBox(self._("Ses"))
        grid = QGridLayout(audio)
        self.source_combo = QComboBox()
        _fit_combo(self.source_combo, 20)
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("⟳")
        self.refresh_btn.setToolTip(self._("Cihaz listesini yenile"))
        self.refresh_btn.clicked.connect(self._refresh_devices)
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(8)
        self.output_combo = QComboBox()
        _fit_combo(self.output_combo, 20)
        self.dub_slider = QSlider(Qt.Orientation.Horizontal)
        self.dub_slider.setRange(0, 150)
        self.orig_slider = QSlider(Qt.Orientation.Horizontal)
        self.orig_slider.setRange(0, 100)
        self.dub_value = QLabel()
        self.orig_value = QLabel()
        for w in (self.dub_value, self.orig_value):
            w.setMinimumWidth(40)

        grid.addWidget(QLabel(self._("Kaynak")), 0, 0)
        grid.addWidget(self.source_combo, 0, 1, 1, 4)
        grid.addWidget(self.refresh_btn, 0, 5)
        grid.addWidget(self.level_bar, 1, 1, 1, 4)
        grid.addWidget(QLabel(self._("Çıkış")), 2, 0)
        grid.addWidget(self.output_combo, 2, 1, 1, 4)
        grid.addWidget(QLabel(self._("Dublaj sesi")), 3, 0)
        grid.addWidget(self.dub_slider, 3, 1)
        grid.addWidget(self.dub_value, 3, 2)
        grid.addWidget(QLabel(self._("Orijinal ses")), 3, 3)
        grid.addWidget(self.orig_slider, 3, 4)
        grid.addWidget(self.orig_value, 3, 5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)
        layout.addWidget(audio)

        translation_box = QGroupBox(self._("Çeviri"))
        row = QHBoxLayout(translation_box)
        self.src_lang = QComboBox()
        _fit_combo(self.src_lang, 11)
        self.src_lang.setAccessibleName(self._("Kaynak dil"))
        _add_option(self.src_lang, self._(display_name(AUTO)), AUTO)
        self.tgt_lang = QComboBox()
        _fit_combo(self.tgt_lang, 11)
        self.tgt_lang.setAccessibleName(self._("Hedef dil"))
        for code, name, _ in LANGUAGES:
            if source_language_supported(code):
                _add_option(self.src_lang, name, code)
            _add_option(self.tgt_lang, name, code)
        saved_source = self.settings.source_lang
        if saved_source and self.src_lang.findData(saved_source) < 0:
            label = display_name(saved_source)
            if not source_language_supported(saved_source):
                label = self._("{language} (desteklenmiyor)", language=label)
            _add_option(self.src_lang, label, saved_source)
        self.engine_combo = QComboBox()
        _fit_combo(self.engine_combo, 13)
        for key, label in ENGINE_LABELS.items():
            _add_option(self.engine_combo, self._(label), key)
        self.settings_btn = QPushButton(self._("Ayarlar…"))
        self.settings_btn.clicked.connect(self._open_settings)
        row.addWidget(self.src_lang)
        row.addWidget(QLabel("→"))
        row.addWidget(self.tgt_lang)
        row.addSpacing(16)
        row.addWidget(QLabel(self._("Motor")))
        row.addWidget(self.engine_combo, 1)
        row.addWidget(self.settings_btn)
        layout.addWidget(translation_box)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #b36b00;")
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        self.test_btn = QPushButton(self._("Ses testi"))
        self.test_btn.setToolTip(self._("API kullanmadan çıkışta bip çalar ve giriş seviyesini gösterir"))
        self.test_btn.clicked.connect(self._audio_test)
        self.start_btn = QPushButton()
        self.start_btn.setMinimumHeight(44)
        bold = QFont(self.start_btn.font())
        bold.setPointSize(bold.pointSize() + 3)
        bold.setBold(True)
        self.start_btn.setFont(bold)
        self.start_btn.clicked.connect(self._toggle)
        buttons.addWidget(self.test_btn)
        buttons.addWidget(self.start_btn, 1)
        layout.addLayout(buttons)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for title, attr, placeholder in (
            (self._("Duyulan"), "source_view", self._("Kaynak konuşmanın metni burada görünecek")),
            (self._("Çeviri (dublaj)"), "target_view", self._("Seslendirilen çeviri burada görünecek")),
        ):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            header = QLabel(title)
            header.setStyleSheet("font-weight: bold;")
            view = getattr(self, attr, None)
            if view is None:
                view = LiveText(placeholder)
                setattr(self, attr, view)
            else:
                view.setPlaceholderText(placeholder)
            box_layout.addWidget(header)
            box_layout.addWidget(view)
            splitter.addWidget(box)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        self.state_label = QLabel(self._("Hazır"))
        self.latency_label = QLabel(self._("Gecikme: {value}", value="–"))
        self.backlog_label = QLabel(self._("Kuyruk: {value}", value="–"))
        status = QStatusBar()
        self.setStatusBar(status)
        status.addPermanentWidget(self.latency_label)
        status.addPermanentWidget(self.backlog_label)
        status.addWidget(self.state_label, 1)

        self.dub_slider.valueChanged.connect(self._volumes_changed)
        self.orig_slider.valueChanged.connect(self._volumes_changed)
        for combo in (self.source_combo, self.output_combo, self.tgt_lang):
            combo.currentIndexChanged.connect(self._update_hints)
        self.src_lang.currentIndexChanged.connect(self._sync_source_language)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self._set_running(False)

    # -- device & settings plumbing -------------------------------------------------------------
    def _refresh_devices(self) -> None:
        current_src = self.source_combo.currentData() if self.source_combo.count() else self.settings.source_device
        current_out = self.output_combo.currentData() if self.output_combo.count() else self.settings.output_device
        self._sources = list_sources()
        self._outputs = list_outputs()
        default = default_output()

        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        _add_option(self.source_combo, self._("Varsayılan mikrofon"), "")
        for dev in self._sources:
            _add_option(self.source_combo, self._device_label(dev), dev.id)
        self._select(self.source_combo, current_src)
        self.source_combo.blockSignals(False)
        self.source_combo.setToolTip(self.source_combo.currentText())

        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        default_label = self._("Varsayılan çıkış ({device})", device=default.name) if default else self._("Varsayılan çıkış")
        _add_option(self.output_combo, default_label, "")
        for dev in self._outputs:
            _add_option(self.output_combo, dev.name, dev.id)
        self._select(self.output_combo, current_out)
        self.output_combo.blockSignals(False)
        self.output_combo.setToolTip(self.output_combo.currentText())
        self._update_hints()

    def _device_label(self, device: Device) -> str:
        if device.id == SYSTEM_LOOPBACK_ID:
            return self._(device.label)
        if device.kind == "loopback":
            return self._("Sistem sesi: {device}", device=device.name)
        if device.kind == "input":
            label = "Sanal kablo: {device}" if device.virtual else "Mikrofon: {device}"
            return self._(label, device=device.name)
        return device.name

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _load_widgets(self) -> None:
        s = self.settings
        self._select(self.source_combo, s.source_device)
        self._select(self.output_combo, s.output_device)
        self._select(self.src_lang, s.source_lang)
        self._select(self.tgt_lang, s.target_lang)
        self._sync_source_language()
        self.dub_slider.setValue(round(s.dub_volume * 100))
        self.orig_slider.setValue(round(s.original_volume * 100))
        self._volumes_changed()

    def _read_widgets(self) -> None:
        self.settings = replace(
            self.settings,
            source_device=self.source_combo.currentData(),
            output_device=self.output_combo.currentData(),
            source_lang=self.src_lang.currentData(),
            target_lang=self.tgt_lang.currentData(),
            dub_volume=self.dub_slider.value() / 100,
            original_volume=self.orig_slider.value() / 100,
        )

    def _save(self) -> None:
        self._read_widgets()
        try:
            self.settings.save()
        except OSError as exc:
            self.statusBar().showMessage(self._("Ayarlar kaydedilemedi: {error}", error=exc), 8000)

    def _volumes_changed(self) -> None:
        self.dub_value.setText(f"{self.dub_slider.value()}%")
        self.orig_value.setText(f"{self.orig_slider.value()}%")
        if self.session:
            self.session.set_volumes(self.dub_slider.value() / 100, self.orig_slider.value() / 100)

    def _current_source(self) -> Device:
        dev_id = self.source_combo.currentData()
        for dev in self._sources:
            if dev.id == dev_id:
                return dev
        return Device("", "default microphone", "input")

    def _current_output(self) -> Device | None:
        dev_id = self.output_combo.currentData()
        for dev in self._outputs:
            if dev.id == dev_id:
                return dev
        return default_output()

    def _sync_source_language(self) -> None:
        source = self.src_lang.currentData()
        with QSignalBlocker(self.engine_combo):
            filtered_index = self.engine_combo.findData(ENGINE_OPENAI_FILTERED)
            self.engine_combo.model().item(filtered_index).setEnabled(source != AUTO)
            self._select(self.engine_combo, effective_engine(replace(self.settings, source_lang=source)))
        self.engine_combo.setToolTip(self.engine_combo.currentText())
        if self.session is None:
            self.engine_combo.setEnabled(source == AUTO)
            self.start_btn.setEnabled(source == AUTO or source_language_supported(source))
        self._update_hints()

    def _on_engine_changed(self) -> None:
        self.settings = replace(self.settings, engine=self.engine_combo.currentData())
        self._update_hints()

    def _update_hints(self) -> None:
        hints = []
        engine = self.engine_combo.currentData()
        target = self.tgt_lang.currentData()
        source_language = self.src_lang.currentData()
        source = self._current_source()
        if source_language != AUTO:
            if not source_language_supported(source_language):
                hints.append(self._("⚠ Kaynak dili desteklenmiyor. Desteklenen bir dil seçin veya otomatik algılamayı kullanın."))
            elif engine == ENGINE_OPENAI_FILTERED:
                hints.append(self._(
                    "ℹ OpenAI yalnızca {language} olarak doğrulanan konuşmayı çevirir ve karışık ya da belirsiz bölümleri atlar. "
                    "Bir OpenAI anahtarı yeterlidir.",
                    language=display_name(source_language),
                ))
            else:
                hints.append(self._(
                    "ℹ Yalnızca {language} olarak algılanan konuşma çevrilir. Kaskad motoru için Deepgram anahtarı ve seçili "
                    "çeviri ile seslendirme sağlayıcılarının anahtarları gerekir.",
                    language=display_name(source_language),
                ))
        elif engine == ENGINE_TRANSLATE and target not in TRANSLATE_MODEL_OUTPUTS:
            hints.append(self._(
                "⚠ Realtime Translate modeli {language} konuşamıyor. "
                "{language} dublaj için 'OpenAI Realtime GPT' veya 'Kaskad' motorunu seçin.",
                language=display_name(target),
            ))
        elif engine == ENGINE_GEMINI:
            hints.append(self._(
                "ℹ Gemini hedef dildeki konuşmayı seslendirmez. Algıladığı diğer dillerdeki konuşmayı çevirir."
            ))
        elif engine == ENGINE_TRANSLATE:
            hints.append(self._("ℹ Bu motor kaynak dili kendisi algılar ve konuşmacı konuşurken çevirir (en düşük gecikme)."))
        elif engine == ENGINE_CASCADE:
            hints.append(self._("ℹ Otomatik dil tanıma için Deepgram Nova-3 kullanın."))
        if (source.kind == "loopback" or source.virtual) and (
            engine == ENGINE_GEMINI or source_language_supported(source_language)
        ):
            hints.append(self._(
                "ℹ Orijinal ses tüm kaynak karışımını ayarlar. "
                "Çevrilmeyen konuşmayı duymak için bu sesi %0'ın üzerinde tutun."
            ))
        _, guard, note = plan_input(self.settings.feedback_guard, source if source.id else None, self._current_output())
        if note:
            hints.append(f"ℹ {self._(SWITCH_NOTE)}")
        elif guard:
            hints.append(self._("ℹ Dublaj sesi kaynağa geri sızabilir: dublaj çalarken giriş susturulacak. Kesintisiz çeviri için "
                         "kulaklık ya da sanal kablo kullanın (README)."))
        if IS_WINDOWS and source.kind == "loopback":
            hints.append(self._("ℹ Orijinal ses: çalışırken diğer uygulamalar bu seviyeye kısılır (%0 = yalnızca dublaj duyulur), "
                         "çeviri etkilenmez; durdurunca sesler eski hâline döner."))
        if IS_MAC and source.virtual:
            hints.append(self._(
                "ℹ Mac'in ses çıkışı {device} olmalı (Sistem Ayarları › Ses › Çıkış). LiveDub'ın Çıkış'ı "
                "hoparlör ya da kulaklık olmalı. Orijinali de duymak için 'Orijinal ses' kaydırıcısını açın.",
                device=source.name,
            ))
        if IS_MAC and not any(d.virtual for d in self._sources):
            hints.append(self._("ℹ macOS'ta sistem sesini (YouTube, Zoom…) çevirmek için ücretsiz BlackHole sürücüsünü kurun (README)."))
        self.hint.setText("\n".join(hints))
        self.hint.setVisible(bool(hints))

    def _open_settings(self) -> None:
        self._read_widgets()
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            previous_language = self.settings.ui_language
            self.settings = dialog.result_settings()
            if self.settings.ui_language != previous_language:
                previous_widget = self.takeCentralWidget()
                self._build()
                self._refresh_devices()
                self._load_widgets()
                previous_widget.deleteLater()
            else:
                self._sync_source_language()
            self._save()

    # -- run control ----------------------------------------------------------------------------
    def _set_running(self, running: bool, test: bool = False) -> None:
        for w in (self.source_combo, self.output_combo, self.refresh_btn, self.src_lang, self.tgt_lang,
                  self.settings_btn, self.test_btn):
            w.setEnabled(not running)
        source = self.src_lang.currentData()
        self.engine_combo.setEnabled(not running and source == AUTO)
        self.start_btn.setEnabled(not test and (running or source == AUTO or source_language_supported(source)))
        self.start_btn.setText(self._("■  Durdur") if running and not test else self._("▶  Başlat"))
        color = "#c0392b" if running and not test else "#1e8449"
        self.start_btn.setStyleSheet(f"QPushButton {{ background: {color}; color: white; border-radius: 6px; }}"
                                     "QPushButton:disabled { background: #888; }")
        if not running:
            self.level_bar.setValue(0)

    def _start_session(self, test: bool) -> None:
        self._save()
        self.session = DubSession(replace(self.settings), lambda kind, data: self.bridge.event.emit(kind, data), test_mode=test)
        self.session.start()
        self._set_running(True, test=test)
        self.state_label.setText(self._("Başlatılıyor…"))

    def _toggle(self) -> None:
        if self.session:
            self.session.stop()
            self.start_btn.setEnabled(False)
            self.start_btn.setText(self._("Durduruluyor…"))
            return
        self.latency_label.setText(self._("Gecikme: {value}", value="–"))
        self._start_session(test=False)

    def _audio_test(self) -> None:
        if not self.session:
            self._start_session(test=True)

    def _on_event(self, kind: str, data: dict) -> None:
        if kind == "level":
            self.level_bar.setValue(int(max(0.0, min(100.0, (data["db"] + 60.0) / 60.0 * 100.0))))
        elif kind == "source_delta":
            self.source_view.delta(data["text"])
        elif kind == "source_partial":
            self.source_view.partial(data["text"])
        elif kind == "source_line":
            self.source_view.line(data["text"])
        elif kind == "source_end":
            self.source_view.end()
        elif kind == "target_delta":
            self.target_view.delta(data["text"])
        elif kind == "target_end":
            self.target_view.end()
        elif kind == "latency":
            self.latency_label.setText(self._("Gecikme: {value}", value=f"{data['ms']} ms"))
        elif kind == "backlog":
            value = f"{data['seconds']:.1f}" + self._(" sn")
            self.backlog_label.setText(self._("Kuyruk: {value}", value=value))
        elif kind == "status":
            self.state_label.setText(translate_message(self.settings.ui_language, data["text"]))
        elif kind == "running":
            self.state_label.setText(self._("Çalışıyor"))
        elif kind == "error":
            self.statusBar().showMessage(f"⚠ {translate_message(self.settings.ui_language, data['text'])}", 10000)
        elif kind == "notice":
            self.statusBar().showMessage(f"ℹ {translate_message(self.settings.ui_language, data['text'])}", 15000)
        elif kind == "input_silent":
            self.hint.setText(f"⚠ {translate_message(self.settings.ui_language, data['text'])}")
            self.hint.setVisible(True)
        elif kind == "input_ok":
            self._update_hints()
        elif kind == "fatal":
            QMessageBox.warning(self, "LiveDub", translate_message(self.settings.ui_language, data["text"]))
        elif kind == "stopped":
            self.session = None
            self._set_running(False)
            self.state_label.setText(self._("Durduruldu"))
            self.backlog_label.setText(self._("Kuyruk: {value}", value="–"))
            self._update_hints()  # drop a silent-input warning from the finished run

    def closeEvent(self, event) -> None:
        self._save()
        if self.session:
            self.session.stop()
            self.session.join(3)
        super().closeEvent(event)


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LiveDub")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "icon.png")))
    window = MainWindow()
    window.show()
    return app.exec()
