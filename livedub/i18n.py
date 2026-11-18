"""Interface strings. Device names, model identifiers and speech stay verbatim."""

from __future__ import annotations

import re


UI_LANGUAGES = (("tr", "Türkçe"), ("en", "English"), ("ru", "Русский"))
_COLUMNS = {"en": 0, "ru": 1}

_LABELS = {
    "Canlı Çeviri ve Dublaj": ("Live Translation and Dubbing", "Перевод и озвучка в реальном времени"),
    "Ayarlar": ("Settings", "Настройки"),
    "Ayarlar…": ("Settings…", "Настройки…"),
    "Genel": ("General", "Общие"),
    "Arayüz dili": ("Interface language", "Язык интерфейса"),
    "API anahtarları": ("API keys", "Ключи API"),
    "OpenAI motorları": ("OpenAI engines", "Движки OpenAI"),
    "Kaskad motoru": ("Cascade engine", "Каскадный движок"),
    "Gelişmiş": ("Advanced", "Дополнительно"),
    "Tamam": ("OK", "ОК"),
    "İptal": ("Cancel", "Отмена"),
    "Ücretsiz Gemini anahtarı al (Google AI Studio)": (
        "Get a free Gemini key (Google AI Studio)", "Получить бесплатный ключ Gemini (Google AI Studio)"
    ),
    "Live Translate modeli": ("Live Translate model", "Модель Live Translate"),
    "Model": ("Model", "Модель"),
    "Ortak": ("Shared", "Общие параметры"),
    "Gürültü azaltma": ("Noise reduction", "Шумоподавление"),
    "Kapalı (sistem sesi için önerilir)": ("Off (recommended for system audio)", "Выкл. (рекомендуется для системного звука)"),
    "Yakın mikrofon / kulaklık mikrofonu": ("Close microphone / headset", "Ближний микрофон / гарнитура"),
    "Uzak mikrofon / oda": ("Distant microphone / room", "Дальний микрофон / помещение"),
    "Realtime Translate (eşzamanlı çeviri)": ("Realtime Translate (simultaneous)", "Realtime Translate (синхронный перевод)"),
    "Kaynak transkript modeli": ("Source transcription model", "Модель распознавания речи"),
    "Realtime GPT (tercüman modu)": ("Realtime GPT (interpreter mode)", "Realtime GPT (режим переводчика)"),
    "Ses": ("Audio", "Звук"),
    "Ses seçimi": ("Voice", "Голос"),
    "Konuşma hızı": ("Speaking speed", "Скорость речи"),
    "Akıl yürütme": ("Reasoning effort", "Глубина рассуждения"),
    "Model varsayılanı": ("Model default", "По умолчанию для модели"),
    "minimal (en hızlı)": ("minimal (fastest)", "minimal (самый быстрый)"),
    "Cümle sonu algılama": ("Speech end detection", "Определение конца реплики"),
    "Sessizliğe göre (server_vad) — en hızlı": (
        "Silence (server_vad), fastest", "По паузе (server_vad), самый быстрый"
    ),
    "Anlama göre (semantic_vad) — daha doğal ama yavaş": (
        "Meaning (semantic_vad), more natural but slower", "По смыслу (semantic_vad), естественнее, но медленнее"
    ),
    "Sessizlik eşiği": ("Silence duration", "Длительность паузы"),
    "VAD hassasiyeti": ("VAD sensitivity", "Чувствительность VAD"),
    "En uzun parça": ("Max segment length", "Макс. длина фрагмента"),
    " sn": (" s", " с"),
    "Deepgram modeli": ("Deepgram model", "Модель Deepgram"),
    "Cümle sonu (endpointing)": ("End-of-speech pause", "Пауза конца реплики"),
    "Çevirmen": ("Translator", "Переводчик"),
    "OpenAI (bağlama duyarlı LLM)": ("OpenAI (context-aware LLM)", "OpenAI (LLM с контекстом)"),
    "DeepL (çok hızlı)": ("DeepL (fast)", "DeepL (быстрый перевод)"),
    "Çeviri modeli (OpenAI)": ("Translation model (OpenAI)", "Модель перевода (OpenAI)"),
    "Metin çeviri modeli": ("Text translation model", "Модель перевода текста"),
    "Seslendirme (TTS)": ("Text-to-speech", "Синтез речи (TTS)"),
    "Windows Live (ücretsiz, çevrimdışı)": ("Windows Live (free, offline)", "Windows Live (бесплатно, офлайн)"),
    "OpenAI TTS modeli": ("OpenAI TTS model", "Модель OpenAI TTS"),
    "OpenAI TTS sesi": ("OpenAI TTS voice", "Голос OpenAI TTS"),
    "ElevenLabs modeli": ("ElevenLabs model", "Модель ElevenLabs"),
    "ElevenLabs ses ID": ("ElevenLabs voice ID", "ID голоса ElevenLabs"),
    "Gecikme birikirse seslendirmeyi hızlandır": (
        "Speed up playback when audio backs up", "Ускорять озвучку при накоплении очереди"
    ),
    "Duyulan konuşmanın metnini göster (OpenAI'da ek transkripsiyon ücreti)": (
        "Show the source transcript (OpenAI charges for transcription)",
        "Показывать текст оригинала (OpenAI тарифицирует распознавание отдельно)",
    ),
    "Geri besleme koruması": ("Feedback protection", "Защита от обратной связи"),
    "Otomatik (önerilir)": ("Auto (recommended)", "Авто (рекомендуется)"),
    "Her zaman açık": ("Always on", "Всегда включена"),
    "Kapalı": ("Off", "Выкл."),
    "Dublajda orijinali kıs": ("Lower original during dubbing", "Приглушать оригинал при озвучке"),
    "Cihaz listesini yenile": ("Refresh audio devices", "Обновить список устройств"),
    "Kaynak": ("Input", "Вход"),
    "Çıkış": ("Output", "Выход"),
    "Dublaj sesi": ("Dub volume", "Громкость озвучки"),
    "Orijinal ses": ("Original volume", "Громкость оригинала"),
    "Çeviri": ("Translation", "Перевод"),
    "Kaynak dil": ("Source language", "Язык оригинала"),
    "Hedef dil": ("Target language", "Язык перевода"),
    "Otomatik algıla": ("Auto-detect", "Автоопределение"),
    "{language} (desteklenmiyor)": ("{language} (unsupported)", "{language} (не поддерживается)"),
    "Motor": ("Engine", "Движок"),
    "Ses testi": ("Audio test", "Проверить звук"),
    "API kullanmadan çıkışta bip çalar ve giriş seviyesini gösterir": (
        "Play a test tone and show the input level without an API call",
        "Воспроизвести сигнал и показать уровень входа без обращения к API",
    ),
    "Duyulan": ("Original", "Оригинал"),
    "Kaynak konuşmanın metni burada görünecek": (
        "The source transcript will appear here", "Здесь появится расшифровка оригинала"
    ),
    "Çeviri (dublaj)": ("Dubbed translation", "Озвученный перевод"),
    "Seslendirilen çeviri burada görünecek": ("The spoken translation will appear here", "Здесь появится текст перевода"),
    "Hazır": ("Ready", "Готово"),
    "Gecikme: {value}": ("Latency: {value}", "Задержка: {value}"),
    "Kuyruk: {value}": ("Queue: {value}", "Очередь: {value}"),
    "Varsayılan mikrofon": ("Default microphone", "Микрофон по умолчанию"),
    "Varsayılan çıkış": ("Default output", "Выход по умолчанию"),
    "Varsayılan çıkış ({device})": ("Default output ({device})", "Выход по умолчанию ({device})"),
    "Sistem sesi: tüm uygulamalar, dublaj hariç (önerilir)": (
        "System audio: all apps except LiveDub (recommended)", "Системный звук: все приложения, кроме LiveDub (рекомендуется)"
    ),
    "Sistem sesi: {device}": ("System audio: {device}", "Системный звук: {device}"),
    "Sanal kablo: {device}": ("Virtual cable: {device}", "Виртуальный кабель: {device}"),
    "Mikrofon: {device}": ("Microphone: {device}", "Микрофон: {device}"),
    "Ayarlar kaydedilemedi: {error}": ("Could not save settings: {error}", "Не удалось сохранить настройки: {error}"),
    "■  Durdur": ("■  Stop", "■  Остановить"),
    "▶  Başlat": ("▶  Start", "▶  Запустить"),
    "Başlatılıyor…": ("Starting…", "Запуск…"),
    "Durduruluyor…": ("Stopping…", "Остановка…"),
    "Çalışıyor": ("Running", "Работает"),
    "Durduruldu": ("Stopped", "Остановлено"),
}

_NOTES = {
    "OpenAI bu modeli seçili kaynak dili modunda metin çevirisi için kullanır.": (
        "OpenAI uses this model to translate text in selected-source-language mode.",
        "OpenAI использует эту модель для перевода текста в режиме выбранного исходного языка.",
    ),
    (
        "Anahtarlar düz metin olarak {path} dosyasında saklanır. Boş bırakılırsa ortam değişkenleri "
        "(GEMINI_API_KEY, OPENAI_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, DEEPL_API_KEY) kullanılır.\n"
        "Gemini motoru için bir Gemini anahtarı yeterlidir. Seçili kaynak diliyle çalışan OpenAI motoru dahil tüm "
        "OpenAI motorları yalnızca OpenAI anahtarı ister. Kaskad için Deepgram ve seçili çeviri sağlayıcısının "
        "anahtarları gerekir. Windows Live seslendirme için ayrı anahtar gerekmez."
    ): (
        "Keys are stored as plain text in {path}. Empty fields use the corresponding environment variables "
        "(GEMINI_API_KEY, OPENAI_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, DEEPL_API_KEY).\n"
        "Gemini needs a Gemini key. OpenAI engines, including selected-language mode, need just an OpenAI key. "
        "Cascade needs Deepgram and a key for the selected translator. Windows Live needs no separate TTS key.",
        "Ключи хранятся в {path} открытым текстом. Для пустых полей используются переменные окружения "
        "(GEMINI_API_KEY, OPENAI_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, DEEPL_API_KEY).\n"
        "Gemini требует ключ Gemini. Для движков OpenAI, включая режим выбранного языка, достаточно ключа OpenAI. "
        "Каскаду нужны ключи Deepgram и выбранного переводчика. Для озвучки Windows Live ключ не нужен.",
    ),
    (
        "Konuşmacı konuşurken çevirir; kaynak dili kendisi algılar, ses tonu konuşmacıya uyarlanır. "
        "Dublaj sesi yakalanan kaynağa geri karışırsa model kendi sesini tekrar çevirip döngüye girer; bu yüzden "
        "sistem sesi için 'Tüm sistem sesi (dublaj hariç)' kaynağını kullanın.\n"
        "Ücret: ücretsiz katmanda ses girişi bedava, çeviri sesi dakikada yaklaşık 0,018 $. Ücretsiz katmanda "
        "gönderilen içerik Google tarafından ürün geliştirmede kullanılabilir."
    ): (
        "Translates as the speaker talks, detects the source language and adapts to their voice. "
        "With system audio, capture all apps except LiveDub to prevent the model from translating its own output.\n"
        "On the free tier, Google may use submitted content to improve its products.",
        "Переводит речь по ходу разговора, определяет исходный язык и подстраивается под голос говорящего. "
        "При захвате системного звука выберите все приложения, кроме LiveDub, иначе модель может переводить собственную озвучку.\n"
        "В бесплатном тарифе Google может использовать отправленный контент для улучшения продуктов.",
    ),
    "Ses tonu konuşmacıya göre otomatik uyarlanır; ses seçimi yoktur. Çıkış dilleri: ": (
        "The voice adapts to the speaker automatically. Supported target languages: ",
        "Голос автоматически подстраивается под говорящего. Поддерживаемые языки перевода: ",
    ),
    (
        "Akıl yürütme ayarı yalnızca gpt-realtime-2 ailesinde geçerlidir. 'En uzun parça': "
        "konuşmacı hiç durmasa bile bu sürede bir çeviri tetiklenir."
    ): (
        "Reasoning effort applies to gpt-realtime-2 models. The maximum segment length sets when translation "
        "starts even if the speaker keeps talking.",
        "Глубина рассуждения применяется к моделям gpt-realtime-2. По достижении максимальной длины фрагмента "
        "перевод запускается даже при непрерывной речи.",
    ),
    "Deepgram anahtarı varken Kaskad seçilirse Nova-3, seçili kaynak dildeki kelimeleri filtreler.": (
        "When Cascade is selected and a Deepgram key is available, Nova-3 filters for words in the selected source language.",
        "Если выбран каскад и задан ключ Deepgram, Nova-3 пропускает на перевод только слова на выбранном исходном языке.",
    ),
    (
        "ElevenLabs Live, çeviri sürerken metin alır. Flash/Turbo v2 ve v2.5 ile çalışır. "
        "Düşük gecikme için Flash v2.5 önerilir."
    ): (
        "ElevenLabs Live receives text while translation is in progress. It works with Flash/Turbo v2 "
        "and v2.5. Use Flash v2.5 for low latency.",
        "ElevenLabs Live получает текст по мере перевода. Поддерживаются Flash/Turbo v2 и v2.5. "
        "Для низкой задержки используйте Flash v2.5.",
    ),
    (
        "Windows Live, hedef dil için Windows'ta yüklü bir sesi kullanır. Seslendirme için API anahtarı gerekmez. "
        "OpenAI çevirisinde ses, çeviri tamamlanmadan başlayabilir."
    ): (
        "Windows Live uses an installed Windows voice for the target language and needs no TTS key. "
        "With OpenAI translation, audio can start while text is still arriving.",
        "Windows Live использует установленный в Windows голос для языка перевода. Ключ для озвучки не нужен. "
        "При переводе через OpenAI звук может начаться до получения всего текста.",
    ),
    (
        "Geri besleme koruması: dublaj sesi yakalanan kaynağa geri sızabiliyorsa (aynı hoparlörün sistem sesi ya da "
        "hoparlörü duyan bir mikrofon), dublaj çalarken giriş susturulur. Bu sırada konuşulanlar kaçabilir; en iyi "
        "sonuç için kulaklık veya sanal kablo (VB-CABLE / BlackHole) kullanın. Otomatik modda, kaynak çıkışla aynı "
        "cihazın sistem sesiyse bunun yerine 'Tüm sistem sesi (dublaj hariç)' yakalanır ve giriş susturulmaz.\n"
        "'Dublajda orijinali kıs': orijinal sesi de çalıyorsanız, dublaj konuşurken orijinalin bu seviyeye inmesi."
    ): (
        "Feedback protection mutes input while the dub plays if it could reach the source. "
        "Speech can be missed during playback. Headphones or a virtual cable (VB-CABLE / BlackHole) prevent this. "
        "In Auto mode, capturing system audio from the output device switches to capture that excludes LiveDub.\n"
        "The original volume drops to the set level while dubbed speech is playing.",
        "Защита от обратной связи приглушает вход, когда озвучка может попасть обратно в источник. "
        "Во время озвучки часть исходной речи может пропасть. Этого можно избежать с наушниками или виртуальным "
        "кабелем (VB-CABLE / BlackHole). В режиме «Авто» при совпадении источника и выхода LiveDub исключает "
        "свой звук из захвата.\nВо время озвучки громкость оригинала снижается до указанного уровня.",
    ),
    (
        "⚠ Realtime Translate modeli {language} konuşamıyor. "
        "{language} dublaj için 'OpenAI Realtime GPT' veya 'Kaskad' motorunu seçin."
    ): (
        "⚠ Realtime Translate cannot dub into {language}. Select OpenAI Realtime GPT or Cascade for this language.",
        "⚠ Realtime Translate не озвучивает язык «{language}». Выберите OpenAI Realtime GPT или каскадный движок.",
    ),
    "⚠ Kaynak dili desteklenmiyor. Desteklenen bir dil seçin veya otomatik algılamayı kullanın.": (
        "⚠ This source language is unsupported. Choose a supported language or Auto-detect.",
        "⚠ Этот язык оригинала не поддерживается. Выберите другой язык или автоопределение.",
    ),
    (
        "ℹ OpenAI yalnızca {language} olarak doğrulanan konuşmayı çevirir ve karışık ya da belirsiz bölümleri atlar. "
        "Bir OpenAI anahtarı yeterlidir."
    ): (
        "ℹ OpenAI translates only speech confirmed as {language} and skips mixed or uncertain segments. "
        "One OpenAI key is enough.",
        "ℹ OpenAI переводит только фрагменты с подтверждённым языком «{language}». Смешанные фрагменты и речь "
        "с неопределённым языком пропускаются. Достаточно одного ключа OpenAI.",
    ),
    (
        "ℹ Yalnızca {language} olarak algılanan konuşma çevrilir. Kaskad motoru için Deepgram anahtarı ve seçili "
        "çeviri ile seslendirme sağlayıcılarının anahtarları gerekir."
    ): (
        "ℹ Only speech detected as {language} is translated. Cascade needs API keys for Deepgram and the "
        "selected translation and voice providers.",
        "ℹ Озвучивается только речь, распознанная на языке «{language}». Каскаду нужны ключи Deepgram и "
        "выбранных сервисов перевода и синтеза речи.",
    ),
    "ℹ Bu motor kaynak dili kendisi algılar ve konuşmacı konuşurken çevirir (en düşük gecikme).": (
        "ℹ This engine detects the source language and translates as the speaker talks.",
        "ℹ Движок определяет исходный язык и переводит по ходу речи.",
    ),
    "ℹ Gemini hedef dildeki konuşmayı seslendirmez. Algıladığı diğer dillerdeki konuşmayı çevirir.": (
        "ℹ Gemini skips speech already in the target language and translates speech it detects in other languages.",
        "ℹ Gemini пропускает речь на языке перевода и переводит распознанную речь на других языках.",
    ),
    "ℹ Otomatik dil tanıma için Deepgram Nova-3 kullanın.": (
        "ℹ Use Deepgram Nova-3 for automatic source language recognition.",
        "ℹ Для автоопределения исходного языка используйте Deepgram Nova-3.",
    ),
    "ℹ Orijinal ses tüm kaynak karışımını ayarlar. Çevrilmeyen konuşmayı duymak için bu sesi %0'ın üzerinde tutun.": (
        "ℹ Original volume controls the entire source mix. Keep it above 0% to hear speech that is filtered out.",
        "ℹ «Громкость оригинала» управляет всем исходным звуком. Оставьте её выше 0%, чтобы слышать речь без перевода.",
    ),
    (
        "ℹ Dublaj sesi kaynağa geri sızabilir: dublaj çalarken giriş susturulacak. Kesintisiz çeviri için "
        "kulaklık ya da sanal kablo kullanın (README)."
    ): (
        "ℹ Dubbed audio could feed back into the input. The input will mute during playback. "
        "Use headphones or a virtual cable for continuous translation.",
        "ℹ Озвучка может попасть обратно на вход. Вход будет приглушён во время воспроизведения. "
        "Для непрерывного перевода используйте наушники или виртуальный кабель.",
    ),
    (
        "ℹ Orijinal ses: çalışırken diğer uygulamalar bu seviyeye kısılır (%0 = yalnızca dublaj duyulur), "
        "çeviri etkilenmez; durdurunca sesler eski hâline döner."
    ): (
        "ℹ Original volume sets the volume of other apps while dubbing (0% plays only the dub). "
        "Translation continues and the original levels are restored when you stop.",
        "ℹ Во время озвучки другие приложения приглушаются до громкости оригинала. "
        "При 0% слышна только озвучка. После остановки уровни восстанавливаются.",
    ),
    (
        "ℹ Mac'in ses çıkışı {device} olmalı (Sistem Ayarları › Ses › Çıkış). LiveDub'ın Çıkış'ı "
        "hoparlör ya da kulaklık olmalı. Orijinali de duymak için 'Orijinal ses' kaydırıcısını açın."
    ): (
        "ℹ Set your Mac output to {device} in System Settings › Sound › Output and select speakers or headphones "
        "as the LiveDub output. Raise the original volume if you also want to hear the source.",
        "ℹ Выберите {device} в меню macOS «Системные настройки → Звук → Выход», а в LiveDub выберите "
        "динамики или наушники. Поднимите громкость оригинала, чтобы слышать и исходный звук.",
    ),
    "ℹ macOS'ta sistem sesini (YouTube, Zoom…) çevirmek için ücretsiz BlackHole sürücüsünü kurun (README).": (
        "ℹ On macOS, install the free BlackHole driver to translate system audio (YouTube, Zoom…).",
        "ℹ На macOS для перевода системного звука (YouTube, Zoom…) установите бесплатный драйвер BlackHole.",
    ),
}

_ENGINE_LABELS = {
    "OpenAI — seçili kaynak dili, tek anahtar": (
        "OpenAI — selected source language, one key",
        "OpenAI — выбранный исходный язык, один ключ",
    ),
    "Gemini Live Translate — eşzamanlı, Türkçe dahil 70+ dil (en ucuz)": (
        "Gemini Live Translate — simultaneous", "Gemini Live Translate — синхронный перевод",
    ),
    "OpenAI Realtime Translate — eşzamanlı (13 çıkış dili, Türkçe yok)": (
        "OpenAI Realtime Translate — simultaneous", "OpenAI Realtime Translate — синхронный перевод",
    ),
    "OpenAI Realtime GPT — tercüman modu, tüm diller": (
        "OpenAI Realtime GPT — interpreter mode", "OpenAI Realtime GPT — режим переводчика",
    ),
    "Kaskad: Deepgram → çeviri → TTS (ElevenLabs/OpenAI ses)": (
        "Cascade: Deepgram → translation → speech", "Каскад: Deepgram → перевод → озвучка",
    ),
}

_MESSAGES = {
    (
        "Kaynak ve çıkış aynı cihaz: dublaj geri karışıp çeviriyi döngüye sokmasın diye "
        "'Tüm sistem sesi (dublaj hariç)' yakalanıyor."
    ): (
        "Input and output use the same device. Capturing system audio without LiveDub prevents a feedback loop.",
        "Вход и выход используют одно устройство. LiveDub исключён из захвата, чтобы озвучка не попадала на вход.",
    ),
    (
        "LiveDub'ın mikrofon izni kapalı. macOS bu yüzden BlackHole dahil tüm girişlerden yalnızca "
        "sessizlik veriyor. Sistem Ayarları › Gizlilik ve Güvenlik › Mikrofon › LiveDub'ı açın ve "
        "uygulamayı yeniden başlatın."
    ): (
        "LiveDub has no microphone access. macOS silences all inputs, including BlackHole. "
        "Allow LiveDub in System Settings › Privacy & Security › Microphone and restart the app.",
        "У LiveDub нет доступа к микрофону. macOS отключает звук на всех входах, включая BlackHole. "
        "Разрешите LiveDub в меню «Системные настройки → Конфиденциальность и безопасность → Микрофон» "
        "и перезапустите приложение.",
    ),
    "Kaynaktan henüz ses gelmiyor. Çevrilecek bir video ya da ses oynatın.": (
        "The source is silent. Play the video or audio to translate.",
        "От источника пока нет сигнала. Включите видео или звук для перевода.",
    ),
    (
        "Mikrofondan hiç ses gelmiyor (tam sessizlik). Mikrofon sessize alınmış ya da uygulamanın "
        "mikrofon izni kapalı olabilir."
    ): (
        "The microphone is silent. Check that it is unmuted and LiveDub has microphone access.",
        "С микрофона не поступает звук. Проверьте, включён ли микрофон и есть ли у LiveDub доступ к нему.",
    ),
    "Seçili kaynak cihaz bulunamadı. Cihaz listesini yenileyin.": (
        "The selected input is unavailable. Refresh the device list.",
        "Выбранный вход недоступен. Обновите список устройств.",
    ),
    "Seçili çıkış cihazı bulunamadı. Cihaz listesini yenileyin.": (
        "The selected output is unavailable. Refresh the device list.",
        "Выбранный выход недоступен. Обновите список устройств.",
    ),
    "Geri besleme koruması açık: dublaj çalarken giriş susturuluyor.": (
        "Feedback protection is on. The input is muted while the dub plays.",
        "Защита от обратной связи включена. Вход приглушается во время озвучки.",
    ),
    "Ses testi: bip sesi çalınıyor, giriş seviyesini izleyin…": (
        "Audio test: playing a tone. Watch the input level…",
        "Проверка звука: воспроизводится сигнал. Следите за уровнем входа…",
    ),
    "Bağlanıyor…": ("Connecting…", "Подключение…"),
    "Oturum yenileniyor…": ("Renewing session…", "Обновление сессии…"),
    "Gemini oturumu yenileniyor…": ("Renewing Gemini session…", "Обновление сессии Gemini…"),
    "Bağlantı kapandı, yeniden bağlanılıyor…": ("Connection closed. Reconnecting…", "Соединение закрыто. Переподключение…"),
    "Gemini oturum kurulumunu onaylamadı; model adını kontrol edin.": (
        "Gemini did not accept the session setup. Check the model name.",
        "Gemini отклонил параметры сессии. Проверьте имя модели.",
    ),
    "RuntimeError: Windows ses yakalamayı başlatmadı (zaman aşımı).": (
        "Windows did not start audio capture before the timeout.",
        "Истекло время ожидания запуска захвата звука в Windows.",
    ),
    "RuntimeError: 'Tüm sistem sesi (dublaj hariç)' için Windows 10 (build 20348+) veya Windows 11 gerekir.": (
        "System audio capture with LiveDub excluded requires Windows 10 build 20348+ or Windows 11.",
        "Для захвата системного звука с исключением LiveDub нужна Windows 10 сборки 20348 или новее либо Windows 11.",
    ),
    "RuntimeError: Sistem sesi yakalama yalnızca Windows'ta doğrudan desteklenir. macOS'ta BlackHole kullanın.": (
        "Direct system audio capture is available on Windows. On macOS, use BlackHole.",
        "Прямой захват системного звука доступен на Windows. На macOS используйте BlackHole.",
    ),
}

_DYNAMIC_MESSAGES = {
    r"Bağlandı: (?P<detail>.+)": ("Connected: {detail}", "Подключено: {detail}"),
    r"Deepgram Nova-3 bu kaynak dili desteklemiyor: (?P<language>.+)": (
        "Deepgram Nova-3 does not support the source language {language}.",
        "Deepgram Nova-3 не поддерживает исходный язык «{language}».",
    ),
    r"Varsayılan çıkış bir sanal kablo \((?P<device>.+)\); dublaj (?P<output>.+) üzerinden çalınıyor\.": (
        "The default output is a virtual cable ({device}). The dub plays through {output}.",
        "Выход по умолчанию — виртуальный кабель ({device}). Озвучка воспроизводится через {output}.",
    ),
    (
        r"(?P<device>.+) üzerinden hiç ses gelmiyor\. Mac'in ses çıkışını .+ yapın "
        r"\(Sistem Ayarları › Ses › Çıkış\) ve bir şey oynatın\. Sürüyorsa: Sistem Ayarları › "
        r"Gizlilik ve Güvenlik › Mikrofon › LiveDub açık olmalı\."
    ): (
        "No signal from {device}. Set your Mac output to {device} in System Settings › Sound › Output and play "
        "the source. If it stays silent, check microphone access for LiveDub in System Settings › Privacy & Security.",
        "Нет сигнала от {device}. Выберите {device} в меню «Системные настройки → Звук → Выход» и "
        "включите звук. Если сигнала нет, проверьте доступ LiveDub к микрофону в настройках конфиденциальности.",
    ),
    (
        r"(?P<device>.+) üzerinden hiç ses gelmiyor\. Çevrilecek uygulamanın çıkışını bu sanal kabloya "
        r"yönlendirin ve bir şey oynatın\."
    ): (
        "No signal from {device}. Route the source app's audio output to this virtual cable and play audio.",
        "Нет сигнала от {device}. Направьте выход приложения в этот виртуальный кабель и включите звук.",
    ),
    r"Ses yakalama durdu: (?P<detail>.+)": ("Audio capture stopped: {detail}", "Захват звука остановился: {detail}"),
    r"RuntimeError: Ses cihazı bulunamadı: (?P<detail>.+)": (
        "Audio device not found: {detail}", "Аудиоустройство не найдено: {detail}",
    ),
    r"(?P<provider>.+) API anahtarı eksik\. Ayarlar > API anahtarları bölümünden girin\.": (
        "Enter a {provider} API key in Settings → API keys.",
        "Введите ключ API {provider} в меню «Настройки → Ключи API».",
    ),
    r"(?P<provider>.+) API anahtarı reddedildi \(HTTP (?P<code>\d+)\)\.\s*(?P<detail>.*)": (
        "{provider} API key rejected (HTTP {code}). {detail}", "{provider} отклонил ключ API (HTTP {code}). {detail}",
    ),
    r"(?P<provider>.+) isteği reddetti \(HTTP (?P<code>\d+)\); model adı/dil ayarını kontrol edin\.\s*(?P<detail>.*)": (
        "{provider} rejected the request (HTTP {code}). Check the model and language. {detail}",
        "{provider} отклонил запрос (HTTP {code}). Проверьте модель и язык. {detail}",
    ),
    r"(?P<provider>.+) API anahtarı geçersiz \((?P<detail>.*)\)\.": (
        "{provider} API key is invalid ({detail}).", "Недействительный ключ API {provider} ({detail}).",
    ),
    r"(?P<provider>.+) oturumu reddetti: (?P<detail>.+)": (
        "{provider} rejected the session: {detail}", "{provider} отклонил сессию: {detail}",
    ),
    (
        r"(?P<provider>.+) sunucusunun SSL sertifikası doğrulanamadı: (?P<detail>.+)\. "
        r"Antivirüs/VPN HTTPS denetimi yapıyorsa kapatmayı deneyin\."
    ): (
        "Could not verify the {provider} SSL certificate: {detail}. Check whether a proxy or VPN inspects HTTPS traffic.",
        "Не удалось проверить SSL-сертификат {provider}: {detail}. Проверьте, перехватывает ли HTTPS прокси или VPN.",
    ),
    r"Bağlantı koptu, yeniden bağlanılıyor: (?P<detail>.+)": (
        "Connection dropped. Reconnecting: {detail}", "Связь потеряна. Переподключение: {detail}",
    ),
    r"Bağlantı kurulamadı: (?P<detail>.+)": ("Could not connect: {detail}", "Не удалось подключиться: {detail}"),
    r"Yanıt başarısız: (?P<detail>.+)": ("Response failed: {detail}", "Ошибка ответа: {detail}"),
    r"Çeviri hatası: (?P<detail>.+)": ("Translation error: {detail}", "Ошибка перевода: {detail}"),
    r"TTS hatası: (?P<detail>.+)": ("Speech synthesis error: {detail}", "Ошибка синтеза речи: {detail}"),
    (
        r"(?P<language>.+) bu modelin desteklediği çıkış dilleri arasında değil; "
        r"sonuç alamazsanız 'OpenAI Realtime' motorunu seçin\."
    ): (
        "The model cannot dub into {language}. Select OpenAI Realtime GPT.",
        "Модель не озвучивает язык «{language}». Выберите OpenAI Realtime GPT.",
    ),
}
_DYNAMIC_PATTERNS = [(re.compile(pattern, re.DOTALL), labels) for pattern, labels in _DYNAMIC_MESSAGES.items()]
_STRINGS = _LABELS | _NOTES | _ENGINE_LABELS | _MESSAGES


def translate(language: str, source: str, /, **values) -> str:
    index = _COLUMNS.get(language)
    labels = _STRINGS.get(source)
    template = labels[index] if index is not None and labels is not None else source
    return template.format(**values) if values else template


def translate_message(language: str, message: str) -> str:
    index = _COLUMNS.get(language)
    if index is not None:
        if message in _STRINGS:
            return _STRINGS[message][index]
        for pattern, labels in _DYNAMIC_PATTERNS:
            if match := pattern.fullmatch(message):
                return labels[index].format(**match.groupdict()).strip()
    return message
