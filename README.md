<div align="center">

# ⚡ AURA DOWNLOADER
### Next-Gen Liquid Glass Media Workstation for Windows

*Универсальный высокопроизводительный комбайн для скачивания, нарезки, кадрирования и AI-улучшения медиафайлов с YouTube, TikTok, Instagram, VK, Twitter, Twitch.*

<br/>

<a href="https://github.com/csezet/aura-downloader/archive/refs/heads/main.zip">
  <img src="https://img.shields.io/badge/📥_СКАЧАТЬ_AURA_DOWNLOADER-Windows_x64-ffffff?style=for-the-badge&logo=windows&logoColor=000000" alt="Скачать Aura Downloader" height="46">
</a>
&nbsp;&nbsp;
<a href="https://github.com/csezet/aura-downloader/releases">
  <img src="https://img.shields.io/badge/📦_РЕЛИЗЫ_И_ОБНОВЛЕНИЯ-GitHub-18181b?style=for-the-badge&logo=github&logoColor=ffffff" alt="Релизы" height="46">
</a>

<br/><br/>

[![Windows](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-18181b?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/csezet/aura-downloader)
[![Python](https://img.shields.io/badge/Python-3.10%2B-18181b?style=for-the-badge&logo=python&logoColor=white)](https://github.com/csezet/aura-downloader)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-18181b?style=for-the-badge&logo=qt&logoColor=white)](https://github.com/csezet/aura-downloader)
[![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp%20%2B%20FFmpeg-18181b?style=for-the-badge&logo=github&logoColor=white)](https://github.com/csezet/aura-downloader)
[![AI](https://img.shields.io/badge/AI-RIFE%2060%20FPS-18181b?style=for-the-badge&logo=nvidia&logoColor=white)](https://github.com/csezet/aura-downloader)
[![License](https://img.shields.io/badge/License-MIT-18181b?style=for-the-badge)](LICENSE)

</div>

---

## ✨ Ключевые возможности

### 🎨 Дизайн и интерфейс
- 🪟 **Liquid Glass & Acrylic Blur**: Настоящее аппаратное размытие рабочего стола Windows DWM (`dwmapi.dll`) позади окна с регулировкой прозрачности.
- 🖤 **Monochrome Cyber-Minimalism**: Чистая высококонтрастная черно-белая эстетика, плавная инверсия кнопок и векторные SVG-пиктограммы.
- 📐 **Идеальная геометрия (12-18px)**: Все окна (Главное, Настройки, История, Пакетная загрузка, Плейлисты) обладают аппаратным сглаживанием DWM без острых краев.
- 🔇 **100% запуск без консоли**: Бесшумный запуск через VBS/`.exe` без всплывающих черных окон терминала.

### 📥 Загрузка и форматы
- 🎬 **Ultra-HD Video (до 4K/8K 60fps)**: Скачивание видеопотоков в максимальном качестве с объединением через FFmpeg.
- 📑 **Умные плейлисты YouTube**: Распознавание ссылок на плейлисты с интерактивным окном выбора роликов чекбоксами.
- 💬 **Субтитры (.srt / .vtt)**: Автоматическое сохранение оригинальных субтитров и автоперевода (RU / EN).
- 🎵 **Hi-Res Audio Extractor**: Извлечение звука в **MP3 (320 kbps)**, **FLAC (Lossless)**, **M4A (AAC)**, **OPUS**, **WAV** с вшиванием ID3-тегов и обложки.
- 📱 **TikTok Без водяных знаков**: Оригинальные ролики без водяных знаков и логотипов.
- 📸 **Instagram Reels & Stories**: Прямая загрузка рилсов, постов и историй.
- 🍪 **Импорт Cookies**: Авторизация через Chrome, Edge, Firefox, Brave, Opera, Яндекс для 18+ и приватных видео.
- 📦 **Пакетная загрузка (Multi-URL Queue)**: Загрузка списка ссылок в очередь одной кнопкой.

### ✂️ Видеостудия и AI-инструменты
- ✂️ **Timecode Trimmer**: Вырезание точного фрагмента по таймкодам без необходимости скачивать весь ролик целиком.
- 📐 **Интерактивный Crop**: Кадрирование под форматы **9:16 (Reels/Shorts/TikTok)**, **1:1 (Квадрат)**, **16:9**, **4:5** с сеткой третей.
- ⚡ **AI Повышение плавности (60 / 120 FPS)**: Интерполяция кадров нейросетью RIFE (Vulkan GPU) для превращения 24/30 FPS исходников в кинематографичные 60/120 FPS.
- 📂 **Local Studio (Drag & Drop)**: Перетаскивание локальных видеофайлов и папок с компьютера для моментальной обработки.
- 💬 **Сжатие для Discord (< 8 МБ)**: Автоматический расчет битрейта под лимиты Discord и Telegram.
- 👾 **Конвертер в GIF**: Создание легковесных анимаций высокого качества.
- 🔔 **Уведомления Windows**: Всплывающие уведомления в Центре уведомлений Windows с быстрым открытием файла по клику.

---

## ⌨️ Горячие клавиши

### ✂️ Окно нарезки (Trim Dialog)
| Клавиша | Действие |
| :--- | :--- |
| `Space` | Воспроизведение / Пауза |
| `I` | Установить начало отрезка (In Point) |
| `O` | Установить конец отрезка (Out Point) |
| `←` / `→` | Точный шаг по таймлайну (±1 кадр) |
| `Home` / `End` | Переход в начало / конец видео |
| `Enter` | Применить нарезку |
| `Esc` | Закрыть окно |

### 📐 Окно кадрирования (Crop Dialog)
| Клавиша | Пресет |
| :--- | :--- |
| `0` | Свободный выбор (Free) |
| `1` | Квадрат 1:1 (Instagram Post) |
| `2` | Вертикальный 9:16 (Reels, TikTok, Shorts) |
| `3` | Горизонтальный 16:9 (YouTube) |
| `4` | Портрет 4:5 |
| `R` | Сброс рамки |

---

## 🚀 Установка и запуск

### Вариант 1: Сборка в автономный `.exe` (PyInstaller)
Для получения готового `AuraDownloader.exe`, не требующего установленного Python:
```bash
python build_exe.py
```
Готовый исполняемый файл появится в папке `dist/AuraDownloader/AuraDownloader.exe`.

---

### Вариант 2: Запуск из исходного кода

#### 1. Клонирование репозитория
```bash
git clone https://github.com/csezet/aura-downloader.git
cd aura-downloader
```

#### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

#### 3. Создание ярлыка на Рабочем столе
```bash
python create_shortcut.py
```

#### 4. Запуск приложения
- Двойной клик по иконке **`Aura Downloader`** на вашем Рабочем столе.
- Или команда: `pythonw main.pyw` / `wscript.exe run.vbs`.

---

## 🛠️ Стек технологий

| Компонент | Технология |
| :--- | :--- |
| **GUI Framework** | PySide6 (Qt 6 for Python) |
| **Window Effects** | Windows DWM API / Acrylic BlurBehind (`dwmapi.dll`) |
| **Download Engine** | yt-dlp |
| **Media Processing** | FFmpeg & FFprobe (Hardware NVENC/MF/QuickSync) |
| **AI Interpolation** | RIFE (Real-Time Intermediate Flow Estimation) via Vulkan |
| **Vector Icons** | High-DPI Lucide / Phosphor Vector SVGs |
| **Notifications** | Windows 10/11 Action Center via QSystemTrayIcon |
| **Packaging** | PyInstaller 6+ |

---

## 📜 Лицензия

Проект распространяется под открытой лицензией MIT. Подробнее см. в файле [LICENSE](LICENSE).

<div align="center">
  <b>Designed with ❤️ in Cyber-Minimalism & Liquid Glass Aesthetic</b>
</div>
