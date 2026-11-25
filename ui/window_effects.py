import os
import ctypes
from ctypes import c_int, c_uint, c_void_p, c_wchar_p, Structure, sizeof, byref
from ctypes import wintypes


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
        user32 = ctypes.windll.user32
        user32.GetWindowLongW.argtypes = [wintypes.HWND, c_int]
        user32.GetWindowLongW.restype = wintypes.LONG
        user32.SetWindowLongW.argtypes = [wintypes.HWND, c_int, wintypes.LONG]
        user32.SetWindowLongW.restype = wintypes.LONG
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, c_int, c_int, c_int, c_int, c_uint]
        user32.SetWindowPos.restype = wintypes.BOOL

        hwnd_p = wintypes.HWND(hwnd)
        style = user32.GetWindowLongW(hwnd_p, GWL_STYLE)
        user32.SetWindowLongW(
            hwnd_p,
            GWL_STYLE,
            style | WS_THICKFRAME | WS_CAPTION | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        )
        user32.SetWindowPos(
            hwnd_p, None, 0, 0, 0, 0,
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


def _configure_icon_apis(user32):
    user32.LoadImageW.argtypes = [c_void_p, c_wchar_p, c_uint, c_int, c_int, c_uint]
    user32.LoadImageW.restype = c_void_p
    user32.SendMessageW.argtypes = [wintypes.HWND, c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.DestroyIcon.argtypes = [c_void_p]
    user32.DestroyIcon.restype = wintypes.BOOL
    set_class = getattr(user32, 'SetClassLongPtrW', None) or getattr(user32, 'SetClassLongW', None)
    if set_class is not None:
        set_class.argtypes = [wintypes.HWND, c_int, c_void_p]
        set_class.restype = c_void_p
    return set_class


def set_native_window_icon(hwnd: int, icon_path: str):
    """
    Sets the native Win32 icons (both big 32/48px and small 16px) on the window HWND.
    Ensures the Windows Taskbar, Alt+Tab, and title area show the exact icon even for
    custom frameless DWM windows without mutating the shared Qt window class icon.
    """
    if not icon_path or not os.path.exists(icon_path):
        return None, None
    try:
        user32 = ctypes.windll.user32
        _configure_icon_apis(user32)
        h_icon_big = user32.LoadImageW(
            None, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        h_icon_small = user32.LoadImageW(
            None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )

        hwnd_p = wintypes.HWND(hwnd)
        if h_icon_big:
            user32.SendMessageW(hwnd_p, WM_SETICON, ICON_BIG, h_icon_big)
        if h_icon_small:
            user32.SendMessageW(hwnd_p, WM_SETICON, ICON_SMALL, h_icon_small)

        return h_icon_big, h_icon_small
    except Exception as e:
        print(f"Failed to set native window icon: {e}")
        return None, None


def destroy_native_icons(h_icon_big=None, h_icon_small=None, hwnd: int = None):
    """Detach and release native Win32 HICON handles allocated via LoadImageW."""
    try:
        user32 = ctypes.windll.user32
        _configure_icon_apis(user32)
        if hwnd:
            hwnd_p = wintypes.HWND(hwnd)
            if h_icon_big:
                user32.SendMessageW(hwnd_p, WM_SETICON, ICON_BIG, 0)
            if h_icon_small:
                user32.SendMessageW(hwnd_p, WM_SETICON, ICON_SMALL, 0)
        for handle in (h_icon_big, h_icon_small):
            if handle:
                user32.DestroyIcon(c_void_p(handle))
    except Exception:
        pass


def apply_acrylic_effect(hwnd: int, gradient_color: int = 0x400A0D12, icon_path: str = None, enable_blur: bool = True):
    """
    Applies real Acrylic frosted blur (when enable_blur=True), native Windows 11 rounded corners,
    and native DWM animations.
    """
    try:
        enable_native_window_animations(hwnd)

        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, c_void_p]
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, c_uint, c_void_p, c_uint]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd_p = wintypes.HWND(hwnd)

        # 1. Extend DWM frame into client area for seamless rounded corners (ELIMINATES BLACK SQUARES!)
        try:
            margins = MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd_p, byref(margins))
        except Exception:
            pass

        # 2. Dark Mode frame
        dark_mode = c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd_p,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_mode),
            sizeof(dark_mode)
        )

        # 3. Force Windows 11 Native Rounded Corners (ELIMINATES BLACK SQUARES!)
        corner_pref = c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            hwnd_p,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(corner_pref),
            sizeof(corner_pref)
        )

        # 4. Windows 11 System Backdrop (Acrylic or None)
        backdrop_type = c_int(DWMSBT_TRANSIENTWINDOW if enable_blur else DWMSBT_NONE)
        dwmapi.DwmSetWindowAttribute(
            hwnd_p,
            DWMWA_SYSTEMBACKDROP_TYPE,
            byref(backdrop_type),
            sizeof(backdrop_type)
        )

        # 5. Windows 10 & 11 Acrylic BlurBehind via SetWindowCompositionAttribute
        user32 = ctypes.windll.user32
        set_window_composition_attribute = getattr(user32, 'SetWindowCompositionAttribute', None)
        if set_window_composition_attribute:
            set_window_composition_attribute.argtypes = [wintypes.HWND, c_void_p]
            set_window_composition_attribute.restype = wintypes.BOOL
            accent = ACCENT_POLICY()
            accent.AccentState = 4 if enable_blur else 0  # 4 = ACCENT_ENABLE_ACRYLICBLURBEHIND, 0 = ACCENT_DISABLED
            accent.AccentFlags = 2 if enable_blur else 0
            accent.GradientColor = gradient_color if enable_blur else 0
            accent.AnimationId = 0

            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = 19  # WCA_ACCENT_POLICY
            data.Data = ctypes.cast(byref(accent), c_void_p)
            data.SizeOfData = sizeof(accent)

            set_window_composition_attribute(hwnd_p, byref(data))
            return True
    except Exception as e:
        print(f"Failed to apply DWM acrylic effect: {e}")
        return False
