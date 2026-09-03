import ctypes
from ctypes import c_int, c_void_p, Structure, sizeof, byref

class ACCENT_POLICY(Structure):
    _fields_ = [
        ('AccentState', c_int),
        ('AccentFlags', c_int),
        ('GradientColor', c_int),
        ('AnimationId', c_int)
    ]

class WINDOWCOMPOSITIONATTRIBDATA(Structure):
    _fields_ = [
        ('Attribute', c_int),
        ('Data', c_void_p),
        ('SizeOfData', c_int)
    ]

# DWM Constants
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38

# Corner preferences (Windows 11)
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

# Backdrop types
DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2      # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4     # Tabbed

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

def enable_native_window_animations(hwnd: int):
    """
    Enables Windows 11 DWM smooth minimize/restore animations and taskbar transitions.
    """
    try:
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            GWL_STYLE,
            style | WS_THICKFRAME | WS_CAPTION | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        )
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
        )
    except Exception:
        pass

class MARGINS(Structure):
    _fields_ = [
        ('cxLeftWidth', c_int),
        ('cxRightWidth', c_int),
        ('cyTopHeight', c_int),
        ('cyBottomHeight', c_int)
    ]

def apply_acrylic_effect(hwnd: int, gradient_color: int = 0x400A0D12):
    """
    Applies real Acrylic frosted blur, native Windows 11 rounded corners, and native DWM animations.
    """
    try:
        enable_native_window_animations(hwnd)

        # Extend DWM frame into client area for flawless anti-aliased rounded corners
        try:
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))
        except Exception:
            pass

        # 1. Dark Mode frame
        dark_mode = c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_mode),
            sizeof(dark_mode)
        )

        # 2. Force Windows 11 Native Rounded Corners (Eliminates black square corner artifacts!)
        corner_pref = c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(corner_pref),
            sizeof(corner_pref)
        )

        # 3. Windows 11 System Backdrop (Acrylic)
        backdrop_type = c_int(DWMSBT_TRANSIENTWINDOW)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            byref(backdrop_type),
            sizeof(backdrop_type)
        )

        # 4. Windows 10 & 11 Acrylic BlurBehind via SetWindowCompositionAttribute
        user32 = ctypes.windll.user32
        set_window_composition_attribute = getattr(user32, 'SetWindowCompositionAttribute', None)
        if set_window_composition_attribute:
            accent = ACCENT_POLICY()
            accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags = 2
            accent.GradientColor = gradient_color
            accent.AnimationId = 0

            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = 19  # WCA_ACCENT_POLICY
            data.Data = ctypes.cast(byref(accent), c_void_p)
            data.SizeOfData = sizeof(accent)

            set_window_composition_attribute(hwnd, byref(data))
            return True
    except Exception as e:
        print(f"Failed to apply DWM acrylic effect: {e}")
        return False
