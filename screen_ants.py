"""Single entry point for the packaged Screen Ants app.

Run with no arguments  -> opens the control panel.
Run with --screensaver -> runs the ant overlay (the control panel launches this).
"""
import sys
import ctypes


def _set_dpi_aware():
    """Make GetSystemMetrics / cursor coords match physical pixels (what PIL's
    ImageGrab uses), so the overlay and screen-capture line up on scaled displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor-v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _set_dpi_aware()
    if "--screensaver" in sys.argv:
        from ants_screensaver import run_screensaver
        run_screensaver()
    else:
        from ants_control_panel import run_panel
        run_panel()


if __name__ == "__main__":
    main()
