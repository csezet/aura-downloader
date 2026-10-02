import os
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


WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
GCLP_HICON = -14
GCLP_HICONSM = -34

def set_native_window_icon(hwnd: int, icon_path: str):
    """
    Sets the native Win32 icons (both big 32/48px and small 16px) on the window HWND
    and window class. Ensures the Windows Taskbar, Alt+Tab, and title area show the
    exact icon even for custom frameless DWM windows.
    """
    if not icon_path or not os.path.exists(icon_path):
        return None, None
    try:
        user32 = ctypes.windll.user32
        h_icon_big = user32.LoadImageW(
            None, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        h_icon_small = user32.LoadImageW(
            None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )

        SetClassLongPtr = getattr(user32, 'SetClassLongPtrW', None) or getattr(user32, 'SetClassLongW')

        if h_icon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
            try:
                SetClassLongPtr(ctypes.c_void_p(hwnd), GCLP_HICON, ctypes.c_void_p(h_icon_big))
            except Exception:
                pass

        if h_icon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)
            try:
                SetClassLongPtr(ctypes.c_void_p(hwnd), GCLP_HICONSM, ctypes.c_void_p(h_icon_small))
            except Exception:
                pass

        return h_icon_big, h_icon_small
    except Exception as e:
        print(f"Failed to set native window icon: {e}")
        return None, None

def apply_acrylic_effect(hwnd: int, gradient_color: int = 0x400A0D12, icon_path: str = None):
    """
    Applies real Acrylic frosted blur, native Windows 11 rounded corners, native DWM animations,
    and sets native Win32 icons for proper Taskbar and Alt+Tab rendering.
    """
    try:
        enable_native_window_animations(hwnd)

        if icon_path:
            set_native_window_icon(hwnd, icon_path)

        # 1. Extend DWM frame into client area for seamless rounded corners (ELIMINATES BLACK SQUARES!)
        try:
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))
        except Exception:
            pass

        # 2. Dark Mode frame
        dark_mode = c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_mode),
            sizeof(dark_mode)
        )

        # 3. Force Windows 11 Native Rounded Corners (ELIMINATES BLACK SQUARES!)
        corner_pref = c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(corner_pref),
            sizeof(corner_pref)
        )

        # 4. Windows 11 System Backdrop (Acrylic)
        backdrop_type = c_int(DWMSBT_TRANSIENTWINDOW)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            byref(backdrop_type),
            sizeof(backdrop_type)
        )

        # 5. Windows 10 & 11 Acrylic BlurBehind via SetWindowCompositionAttribute
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
