<div align="center">

# ⚡ AURA DOWNLOADER

**High-Performance Liquid Glass Media Downloader for Windows**  
*Скачивание видео и аудио в максимальном качестве с YouTube, TikTok, Instagram, VK, Twitter, Twitch.*

[![Windows](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-000000?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/csezet/aura-downloader)
[![Python](https://img.shields.io/badge/Python-3.10%2B-000000?style=for-the-badge&logo=python&logoColor=white)](https://github.com/csezet/aura-downloader)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-000000?style=for-the-badge&logo=qt&logoColor=white)](https://github.com/csezet/aura-downloader)
[![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp%20%2B%20FFmpeg-000000?style=for-the-badge&logo=github&logoColor=white)](https://github.com/csezet/aura-downloader)
[![License](https://img.shields.io/badge/License-MIT-000000?style=for-the-badge)](LICENSE)

</div>

---

## ✨ Особенности и фичи

- 🪟 **Liquid Glass & Acrylic Blur**: Настоящая полупрозрачность Windows DWM с матовым размытием рабочего стола позади окна.
- 🖤 **Monochrome Cyber-Minimalism UI**: Высококонтрастная черно-белая эстетика, тактильная инверсия кнопок и векторные иконки.
- 🎬 **Ultra-HD Video (до 4K/8K 60fps)**: Автоматическое объединение лучших видео- и аудиопотоков без потери качества через FFmpeg.
- 🎵 **Hi-Res Audio Extractor**: Извлечение звука в **MP3 (320 kbps)**, **FLAC (Lossless)**, **M4A (AAC)**, **OPUS**, **WAV** с вшиванием ID3-тегов и оригинальной обложки.
- 📱 **TikTok Без водяных знаков**: Загрузка оригинальных роликов в HD без логотипов.
- 📸 **Instagram Reels & Stories**: Прямая загрузка рилсов, постов и историй.
- ✂️ **Timecode Trimmer**: Скачивание конкретного фрагмента по таймкодам (например, с `00:15` по `01:45`) без скачивания всего видео.
- 📐 **Ручное кадрирование (Crop)**: Интерактивная рамка обрезки границ видео, сетка правила третей и пресеты (`1:1`, `9:16`, `16:9`, `4:5`, `Free`) для создания Reels, TikTok, Shorts и постов.
- 👾 **Конвертер в GIF**: Создание легковесных и качественных GIF-анимаций для мессенджеров.
- 💬 **Сжатие для Discord (< 8 МБ)**: Автоматический расчет битрейта и сжатие под лимит бесплатного Discord.
- 📦 **Пакетная загрузка (Multi-URL Queue)**: Загрузка списка ссылок в очередь одной кнопкой.
- 🍪 **Импорт Cookies**: Поддержка авторизации через Chrome, Edge, Firefox, Brave, Opera для скачивания 18+ и закрытых видео.
- 📋 **Smart Clipboard**: Автоматическое распознавание ссылок из буфера обмена.
- ⚡ **Плавные анимации**: Гладко скользящий прогресс-бар и плавное появление карточек (`Fade & Slide`).
- 🔇 **100% Запуск без консоли**: Бесшумный запуск через `pythonw.exe` / `.exe` без всплывающих окон терминала.

---

## 🚀 Установка и запуск

### 1. Клонирование репозитория
```bash
git clone https://github.com/csezet/aura-downloader.git
cd aura-downloader
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Создание ярлыка на Рабочем столе
```bash
python create_shortcut.py
```

### 4. Бесшумный запуск приложения
- Двойной клик по **`Aura Downloader`** на вашем **Рабочем столе**.
- Или запуск через `pythonw main.pyw` / `run.vbs`.

---

## 🛠️ Стек технологий

| Компонент | Технология |
| :--- | :--- |
| **GUI Framework** | PySide6 (Qt 6 for Python) |
| **Window Effects** | Windows DWM API / Acrylic BlurBehind (`dwmapi.dll`) |
| **Download Engine** | yt-dlp |
| **Media Processing** | FFmpeg & FFprobe |
| **Icons & Vectors** | Lucide / Phosphor Vector SVGs + Pillow |
| **Packaging** | PyInstaller + Windows Shell Script Host |

---

## 📜 Лицензия

Распространяется под лицензией MIT. Подробнее см. в файле [LICENSE](LICENSE).

<div align="center">
  <b>Designed with ❤️ in Cyber-Minimalism Aesthetic</b>
</div>
