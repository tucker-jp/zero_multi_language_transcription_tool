"""macOS native window level utility for fullscreen overlay support."""

from __future__ import annotations

import sys


def configure_overlay_window(widget) -> None:
    """Set macOS NSWindow level and collection behavior so the overlay
    appears above fullscreen apps and on all Spaces.

    No-op on non-macOS platforms. Falls back silently on any error.
    """
    if sys.platform != "darwin":
        return

    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        # Configure objc_msgSend signatures
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]

        # Get the NSView from the Qt widget
        view_ptr = int(widget.winId())

        # [view window] -> NSWindow
        sel_window = objc.sel_registerName(b"window")
        nswindow = objc.objc_msgSend(view_ptr, sel_window)
        if not nswindow:
            return

        # Set window level to kCGScreenSaverWindowLevel (1000)
        # Must be this high to appear above macOS fullscreen Spaces
        kCGScreenSaverWindowLevel = 1000
        sel_setLevel = objc.sel_registerName(b"setLevel:")
        send_with_int = ctypes.cast(
            objc.objc_msgSend,
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long),
        )
        send_with_int(nswindow, sel_setLevel, kCGScreenSaverWindowLevel)

        # Set collection behavior:
        #   NSWindowCollectionBehaviorCanJoinAllSpaces       = 1 << 0  = 1
        #   NSWindowCollectionBehaviorStationary             = 1 << 4  = 16
        #   NSWindowCollectionBehaviorIgnoresCycle           = 1 << 6  = 64
        #   NSWindowCollectionBehaviorFullScreenAuxiliary    = 1 << 8  = 256
        #   NSWindowCollectionBehaviorFullScreenDisallowsTiling = 1 << 12 = 4096
        behavior = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8) | (1 << 12)  # 4433
        sel_setBehavior = objc.sel_registerName(b"setCollectionBehavior:")
        send_with_uint = ctypes.cast(
            objc.objc_msgSend,
            ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong
            ),
        )
        send_with_uint(nswindow, sel_setBehavior, behavior)

    except Exception:
        # Graceful fallback — overlay still works, just not above fullscreen
        pass
