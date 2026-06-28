import tkinter as tk
import subprocess
import os
import sys
import json

# Color Palette (UI theme)
COLOR_BG = "#161616"
COLOR_CARD = "#212121"
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_SUB = "#9E9E9E"
COLOR_RED = "#FF3333"
COLOR_GREEN = "#39FF14"
COLOR_GOLD = "#D89B32"
COLOR_BTN_HOVER_OPEN = "#FF5252"
COLOR_BTN_HOVER_CLOSE = "#4E342E"

# Ant colour choices (must match ANT_PALETTES keys in ants_screensaver.py).
PALETTE_NAMES = ["Red", "Green", "Blue", "Purple", "Orange", "Gold", "Black", "White"]
# Representative swatch colour (the mid/thorax shade of each palette).
PALETTE_SWATCH = {
    "Red": "#E53935", "Green": "#43A047", "Blue": "#1E88E5", "Purple": "#8E24AA",
    "Orange": "#F57C00", "Gold": "#E5A93C", "Black": "#37474F", "White": "#ECEFF1",
}


def app_dir():
    """Directory for read/write files (config.json). Next to the .exe when
    frozen by PyInstaller, otherwise next to this source file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """Path to a bundled read-only resource (e.g. ant.ico)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# Matches the screensaver process in BOTH modes (dev: pythonw + script; frozen:
# the exe launched with --screensaver). The query process is powershell.exe, so
# it never matches itself even though its command line contains these literals.
_PS_FILTER = ("Get-CimInstance Win32_Process | Where-Object { "
              "($_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*ants_screensaver.py*') "
              "-or ($_.Name -eq 'ScreenAnts.exe' -and $_.CommandLine -like '*--screensaver*') }")


def is_screensaver_running():
    """Returns True if the screen-ants overlay process is currently running."""
    try:
        cmd = 'powershell -Command "' + _PS_FILTER + ' | Select-Object -ExpandProperty ProcessId"'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        return len(output.strip()) > 0
    except Exception:
        return False


def kill_screensaver_instances():
    """Stops every running instance of the screen-ants overlay process."""
    try:
        cmd = 'powershell -Command "' + _PS_FILTER + ' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class ControlPanelApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Screen Ants Control Center")
        self.root.geometry("400x560")
        self.root.resizable(False, False)
        self.root.configure(bg=COLOR_BG)
        self.center_window(400, 560)

        ico_path = resource_path("ant.ico")
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        # Header Card
        self.header_frame = tk.Frame(self.root, bg=COLOR_CARD, bd=0)
        self.header_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        self.title_label = tk.Label(
            self.header_frame, text="🐜 Interactive Screen Ants",
            font=("Segoe UI", 14, "bold"), fg=COLOR_GOLD, bg=COLOR_CARD)
        self.title_label.pack(pady=(12, 2))

        self.status_text = tk.StringVar()
        self.status_color = COLOR_RED
        self.update_status_display()
        self.status_label = tk.Label(
            self.header_frame, textvariable=self.status_text,
            font=("Segoe UI", 10, "bold"), fg=self.status_color, bg=COLOR_CARD)
        self.status_label.pack(pady=(0, 12))

        # Config container
        self.config_container = tk.Frame(self.root, bg=COLOR_BG)
        self.config_container.pack(fill=tk.X, padx=20, pady=5)

        # Configuration variables (with defaults)
        self.idle_var = tk.IntVar(value=5)
        self.queen_var = tk.IntVar(value=60)
        self.worker_color_var = tk.StringVar(value="Red")
        self.scout_color_var = tk.StringVar(value="Green")
        self.queen_color_var = tk.StringVar(value="Gold")

        # Load existing config
        self.config_path = os.path.join(app_dir(), "config.json")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    cfg = json.load(f)
                self.idle_var.set(cfg.get("idle_timeout", 5))
                self.queen_var.set(cfg.get("queen_interval", cfg.get("deadlock_timeout", 60)))
                self.worker_color_var.set(cfg.get("worker_color", "Red"))
                self.scout_color_var.set(cfg.get("scout_color", "Green"))
                self.queen_color_var.set(cfg.get("queen_color", "Gold"))
            except Exception:
                pass

        # Sliders
        self.make_slider("Start Idle Delay (sec):", self.idle_var, 2, 60)
        self.make_slider("Queen Outing Time (sec):", self.queen_var, 15, 300)

        # Colour selectors
        self.make_color_row("Worker Color:", self.worker_color_var)
        self.make_color_row("Scout Color:", self.scout_color_var)
        self.make_color_row("Queen Color:", self.queen_color_var)

        # Buttons
        self.btn_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.btn_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 12))

        self.btn_open = tk.Button(
            self.btn_frame, text="▶ Start / Apply", font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN, bg=COLOR_RED, activebackground=COLOR_BTN_HOVER_OPEN,
            activeforeground=COLOR_TEXT_MAIN, bd=0, cursor="hand2", command=self.start_screensaver)
        self.btn_open.pack(fill=tk.X, pady=5, ipady=7)
        self.btn_open.bind("<Enter>", lambda e: self.btn_open.configure(bg=COLOR_BTN_HOVER_OPEN))
        self.btn_open.bind("<Leave>", lambda e: self.btn_open.configure(bg=COLOR_RED))

        self.btn_close = tk.Button(
            self.btn_frame, text="⏹ Stop Screensaver", font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_SUB, bg="#2A2A2A", activebackground=COLOR_BTN_HOVER_CLOSE,
            activeforeground=COLOR_TEXT_MAIN, bd=0, cursor="hand2", command=self.stop_screensaver)
        self.btn_close.pack(fill=tk.X, pady=5, ipady=7)
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(bg=COLOR_BTN_HOVER_CLOSE, fg=COLOR_TEXT_MAIN))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(bg="#2A2A2A", fg=COLOR_TEXT_SUB))

    # ---- UI builders -------------------------------------------------------
    def make_slider(self, label, var, lo, hi):
        frame = tk.Frame(self.config_container, bg=COLOR_BG)
        frame.pack(fill=tk.X, pady=4)
        tk.Label(frame, text=label, font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT_SUB,
                 bg=COLOR_BG, width=18, anchor="w").pack(side=tk.LEFT, padx=(5, 5))
        tk.Scale(frame, from_=lo, to=hi, orient=tk.HORIZONTAL, variable=var,
                 font=("Consolas", 9), fg=COLOR_TEXT_MAIN, bg=COLOR_BG, troughcolor=COLOR_CARD,
                 activebackground=COLOR_RED, highlightthickness=0, bd=0
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))

    def make_color_row(self, label, var):
        frame = tk.Frame(self.config_container, bg=COLOR_BG)
        frame.pack(fill=tk.X, pady=4)
        tk.Label(frame, text=label, font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT_SUB,
                 bg=COLOR_BG, width=18, anchor="w").pack(side=tk.LEFT, padx=(5, 5))

        swatch = tk.Label(frame, bg=PALETTE_SWATCH.get(var.get(), "#888888"), width=3, bd=1, relief="solid")
        swatch.pack(side=tk.RIGHT, padx=(6, 5))

        def on_change(name, *_):
            var.set(name)
            swatch.configure(bg=PALETTE_SWATCH.get(name, "#888888"))

        menu = tk.OptionMenu(frame, var, *PALETTE_NAMES, command=lambda n: on_change(n))
        menu.configure(font=("Segoe UI", 9), fg=COLOR_TEXT_MAIN, bg=COLOR_CARD,
                       activebackground=COLOR_BTN_HOVER_CLOSE, activeforeground=COLOR_TEXT_MAIN,
                       highlightthickness=0, bd=0, width=8)
        menu["menu"].configure(bg=COLOR_CARD, fg=COLOR_TEXT_MAIN)
        menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))

    def center_window(self, width, height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def update_status_display(self):
        running = is_screensaver_running()
        if running:
            self.status_text.set("● Status: Running")
            self.status_color = COLOR_GREEN
        else:
            self.status_text.set("○ Status: Stopped")
            self.status_color = COLOR_TEXT_SUB
        if hasattr(self, 'status_label'):
            self.status_label.configure(fg=self.status_color)

    def save_config(self):
        """Saves all options to config.json."""
        try:
            cfg = {
                "idle_timeout": self.idle_var.get(),
                "queen_interval": self.queen_var.get(),
                "worker_color": self.worker_color_var.get(),
                "scout_color": self.scout_color_var.get(),
                "queen_color": self.queen_color_var.get(),
            }
            with open(self.config_path, "w") as f:
                json.dump(cfg, f)
        except Exception:
            pass

    def start_screensaver(self):
        self.save_config()
        kill_screensaver_instances()

        try:
            if getattr(sys, "frozen", False):
                # Frozen exe: re-launch ourselves in screensaver mode.
                subprocess.Popen([sys.executable, "--screensaver"], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                # Dev mode: run the script with pythonw.
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ants_screensaver.py")
                pythonw_exe = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(pythonw_exe):
                    pythonw_exe = sys.executable
                subprocess.Popen([pythonw_exe, script_path], creationflags=subprocess.CREATE_NO_WINDOW)
            self.show_toast(f"Launched! Ants appear after {self.idle_var.get()}s idle.")
        except Exception as e:
            self.show_toast(f"Failed to launch: {e}")
        self.root.destroy()

    def stop_screensaver(self):
        kill_screensaver_instances()
        self.show_toast("Successfully stopped all screen ants.")
        self.root.destroy()

    def show_toast(self, message):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#333333")
        tk.Label(toast, text=message, font=("Segoe UI", 10, "bold"), fg="#FFFFFF",
                 bg="#333333", padx=15, pady=10).pack()
        toast.update()
        tw, th = toast.winfo_width(), toast.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        toast.geometry(f"{tw}x{th}+{(screen_w - tw) // 2}+{screen_h - th - 100}")
        self.root.after(2000, toast.destroy)
        self.root.update()


def run_panel():
    app = ControlPanelApp()
    app.root.mainloop()


if __name__ == "__main__":
    run_panel()
