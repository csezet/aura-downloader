def get_stylesheet(glass_opacity: float = 0.45) -> str:
    return f"""
    /* Root Window - Transparent to allow rounded anti-aliased corners */
    QMainWindow {{
        background: transparent;
    }}

    /* Global Base */
    QWidget {{
        color: #EDEDED;
        font-family: 'Inter', 'Segoe UI', -apple-system, Roboto, sans-serif;
        font-size: 13px;
        outline: none;
    }}

    /* Main Window Central Glass Panel */
    #CentralWidget {{
        background-color: rgba(10, 13, 18, {glass_opacity});
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.20);
    }}

    /* Title Bar */
    #TitleBar {{
        background-color: transparent;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    
    #AppTitle {{
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 1.5px;
        color: #FFFFFF;
        text-transform: uppercase;
    }}

    #TitleButton {{
        background-color: transparent;
        border: none;
        border-radius: 6px;
        color: #A1A1AA;
        font-size: 13px;
        font-weight: bold;
        min-width: 32px;
        min-height: 28px;
        max-width: 32px;
        max-height: 28px;
        margin: 0px;
        padding: 0px;
    }}
    #TitleButton:hover {{
        background-color: rgba(255, 255, 255, 0.12);
        color: #FFFFFF;
        margin: 0px;
        padding: 0px;
    }}
    #TitleButton:pressed {{
        background-color: rgba(255, 255, 255, 0.20);
        color: #FFFFFF;
        margin: 0px;
        padding: 0px;
    }}
    #CloseButton:hover {{
        background-color: #E81123;
        color: #FFFFFF;
        margin: 0px;
        padding: 0px;
    }}
    #CloseButton:pressed {{
        background-color: #B80D1A;
        color: #FFFFFF;
        margin: 0px;
        padding: 0px;
    }}

    /* Modern Dark ScrollBars */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.18);
        min-height: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(255, 255, 255, 0.35);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        height: 0px;
        background: transparent;
    }}

    /* Glass Cards & Containers */
    .GlassCard {{
        background-color: rgba(255, 255, 255, 0.035);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 10px;
    }}
    .GlassCard:hover {{
        border: 1px solid rgba(255, 255, 255, 0.22);
    }}

    /* URL Input Field */
    QLineEdit#UrlInput {{
        background-color: rgba(0, 0, 0, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 8px;
        padding: 9px 12px;
        color: #FFFFFF;
        font-size: 13px;
        font-family: 'Consolas', 'JetBrains Mono', monospace;
        selection-background-color: #FFFFFF;
        selection-color: #000000;
    }}
    QLineEdit#UrlInput:focus {{
        border: 1px solid #FFFFFF;
        background-color: rgba(0, 0, 0, 0.85);
    }}
    QLineEdit#UrlInput::placeholder {{
        color: #52525B;
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }}

    /* Primary Stark Action Button (Fixed position, NO displacement on click) */
    QPushButton#PrimaryButton {{
        background-color: #FFFFFF;
        color: #000000;
        border: 1px solid #FFFFFF;
        border-radius: 8px;
        padding: 10px 20px;
        margin: 0px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.8px;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: #E4E4E7;
        border: 1px solid #FFFFFF;
        color: #000000;
        padding: 10px 20px;
        margin: 0px;
    }}
    QPushButton#PrimaryButton:pressed {{
        background-color: #A1A1AA;
        border: 1px solid #A1A1AA;
        color: #000000;
        padding: 10px 20px;
        margin: 0px;
    }}
    QPushButton#PrimaryButton:disabled {{
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #52525B;
        padding: 10px 20px;
        margin: 0px;
    }}

    /* Secondary Glass Inverted Buttons (Fixed position, NO displacement on click) */
    QPushButton.GlassButton {{
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 8px;
        color: #EDEDED;
        padding: 7px 12px;
        margin: 0px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton.GlassButton:hover {{
        background-color: #FFFFFF;
        border: 1px solid #FFFFFF;
        color: #000000;
        padding: 7px 12px;
        margin: 0px;
    }}
    QPushButton.GlassButton:pressed {{
        background-color: #D4D4D8;
        border: 1px solid #D4D4D8;
        color: #000000;
        padding: 7px 12px;
        margin: 0px;
    }}

    /* Mode Pill Buttons (Fixed position, NO displacement on click) */
    QPushButton.ModePill {{
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        color: #A1A1AA;
        padding: 6px 12px;
        margin: 0px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.2px;
    }}
    QPushButton.ModePill:hover {{
        background-color: rgba(255, 255, 255, 0.12);
        color: #FFFFFF;
        border: 1px solid rgba(255, 255, 255, 0.25);
        padding: 6px 12px;
        margin: 0px;
    }}
    QPushButton.ModePill[active="true"] {{
        background-color: #FFFFFF;
        border: 1px solid #FFFFFF;
        color: #000000;
        font-weight: 800;
        padding: 6px 12px;
        margin: 0px;
    }}
    QPushButton.ModePill:pressed {{
        padding: 6px 12px;
        margin: 0px;
    }}

    /* ComboBoxes / Dropdowns */
    QComboBox {{
        background-color: rgba(0, 0, 0, 0.75);
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 6px;
        padding: 5px 10px;
        color: #FFFFFF;
        font-size: 12px;
        font-weight: 600;
        min-height: 22px;
    }}
    QComboBox:hover {{
        border: 1px solid #FFFFFF;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: #0E1117;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 6px;
        selection-background-color: #FFFFFF;
        selection-color: #000000;
        padding: 4px;
        color: #EDEDED;
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: rgba(0, 0, 0, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 6px;
        height: 10px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: #FFFFFF;
        border-radius: 5px;
    }}

    /* Labels & Badges */
    QLabel#Badge {{
        background-color: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 4px;
        color: #EDEDED;
        padding: 2px 6px;
        font-size: 11px;
        font-family: 'Consolas', 'JetBrains Mono', monospace;
        font-weight: 700;
    }}
    QLabel#PlatformBadge {{
        background-color: #FFFFFF;
        border: 1px solid #FFFFFF;
        border-radius: 4px;
        color: #000000;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }}

    /* ScrollBars */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.15);
        min-height: 20px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #FFFFFF;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    /* Tooltips */
    QToolTip {{
        background-color: #0E1117;
        color: #FFFFFF;
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 4px;
        padding: 5px 8px;
        font-size: 11px;
    }}
    """
