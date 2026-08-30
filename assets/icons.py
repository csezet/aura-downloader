import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, QSize, Qt

ICONS_SVG = {
    "paste": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>''',
    "batch": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>''',
    "history": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>''',
    "settings": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>''',
    "sparkles": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>''',
    "video": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.934a.5.5 0 0 0-.777-.416L16 11"/><rect width="14" height="12" x="2" y="6" rx="2"/></svg>''',
    "music": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>''',
    "scissors": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>''',
    "gif": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="M7 10h-1a2 2 0 0 0-2 2v0a2 2 0 0 0 2 2h1v-2"/><path d="M12 10v4"/><path d="M16 10h3"/><path d="M16 12h2"/><path d="M16 14h3"/></svg>''',
    "discord": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6h0a14.5 14.5 0 0 0-4-1.2 1 1 0 0 0-.5.2c-.3.4-.6.9-.8 1.4-1.8-.3-3.6-.3-5.4 0-.2-.5-.5-1-.8-1.4a1 1 0 0 0-.5-.2A14.5 14.5 0 0 0 2 6a18.3 18.3 0 0 0-2 13.5 1 1 0 0 0 .5.8 15.6 15.6 0 0 0 4.8 2.4 1 1 0 0 0 1.1-.5c.4-.6.8-1.2 1.1-1.9-1.3-.5-2.4-1.2-3.4-2.1a.5.5 0 0 1 .2-.8c.4.3.7.6 1.1.8 3.5 1.6 7.3 1.6 10.8 0 .4-.3.7-.5 1.1-.8a.5.5 0 0 1 .2.8c-1 .9-2.1 1.6-3.4 2.1.3.7.7 1.3 1.1 1.9a1 1 0 0 0 1.1.5 15.6 15.6 0 0 0 4.8-2.4 1 1 0 0 0 .5-.8A18.3 18.3 0 0 0 22 6"/><circle cx="7.5" cy="13.5" r="1.5" fill="currentColor"/><circle cx="16.5" cy="13.5" r="1.5" fill="currentColor"/></svg>''',
    "mute": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 3 18 18"/><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/></svg>''',
    "download": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>''',
    "folder": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>''',
    "play": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg>''',
    "crop": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/></svg>''',
    "zap": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>''',
}

_pixmap_cache = {}

def get_svg_pixmap(name: str, color: str = "#EDEDED", size: int = 20) -> QPixmap:
    key = f"{name}_{color}_{size}"
    if key in _pixmap_cache:
        return _pixmap_cache[key]

    svg_data = ICONS_SVG.get(name)
    if not svg_data:
        return QPixmap(size, size)

    colored_svg = svg_data.replace('stroke="currentColor"', f'stroke="{color}"').replace('fill="currentColor"', f'fill="{color}"')
    
    renderer = QSvgRenderer(QByteArray(colored_svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    _pixmap_cache[key] = pixmap
    return pixmap

def get_svg_icon(name: str, color: str = "#EDEDED", size: int = 20) -> QIcon:
    return QIcon(get_svg_pixmap(name, color=color, size=size))

def get_dual_state_icon(name: str, size: int = 16) -> QIcon:
    """
    Creates an adaptive QIcon:
    - Normal / Inactive: White (#EDEDED)
    - Active / Hovered / Checked: Pure Black (#000000)
    """
    icon = QIcon()
    pix_white = get_svg_pixmap(name, color="#EDEDED", size=size)
    pix_black = get_svg_pixmap(name, color="#000000", size=size)

    # Inactive / Normal
    icon.addPixmap(pix_white, QIcon.Mode.Normal, QIcon.State.Off)
    # Hover / Active
    icon.addPixmap(pix_black, QIcon.Mode.Active, QIcon.State.Off)
    # Selected / Checked
    icon.addPixmap(pix_black, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(pix_black, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(pix_black, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(pix_black, QIcon.Mode.Selected, QIcon.State.On)

    return icon
