# Компоненты дистрибутива

Код Aura Downloader распространяется под MIT (LICENSE). В архиве EXE находятся отдельные компоненты со своими лицензиями; их тексты скопированы в `licenses/`.

| Компонент | Лицензия и исходники |
| --- | --- |
| Python | PSF: https://www.python.org/downloads/source/ |
| PySide6, Shiboken и Qt | LGPL/GPL либо коммерческая лицензия Qt: https://code.qt.io/cgit/pyside/pyside-setup.git/ и https://code.qt.io/cgit/qt/ |
| yt-dlp | Unlicense: https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | Unlicense: https://github.com/yt-dlp/ejs |
| Deno | MIT: https://github.com/denoland/deno |
| FFmpeg, FFprobe | GPLv3, сборка Gyan essentials: https://www.gyan.dev/ffmpeg/builds/ |
| Pillow | MIT-CMU: https://github.com/python-pillow/Pillow |
| Requests и зависимости | Лицензии в `licenses/`; https://github.com/psf/requests |

Версии Python-пакетов зафиксированы в `requirements-lock.txt`. Сборка копирует тексты лицензий установленных пакетов, включая дополнительные зависимости yt-dlp. Qt остаётся набором отдельных динамических библиотек в `_internal/`, доступных для замены совместимыми версиями.

FFmpeg запускается отдельным процессом. Версия, URL исходников, URL архива и его SHA-256 зафиксированы в `packaging/tools.json`; описание и конфигурация сборки производителя находятся в `licenses/FFmpeg-README.txt`, полный текст GPL — в `licenses/FFmpeg-LICENSE.txt`. Информация о лицензировании FFmpeg: https://ffmpeg.org/legal.html. Для распространения изменённых компонентов соблюдайте условия их лицензий и предоставляйте соответствующие исходники.
