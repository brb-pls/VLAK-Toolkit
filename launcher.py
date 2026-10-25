"""
VLAK Launcher
A retro-styled launcher for the DOS game VLAK, running via DOSBox.

Folder layout expected next to this file:
    launcher.py
    config.json                 <- created automatically (DOSBox path, VLAK folder path)
    metadata.json                <- created automatically (descriptions for packs)
    scn/                          <- your imported custom .SCN files live here
    pcx/                          <- your imported custom .PCX files live here
    ext/                          <- images used by the Level Editor (you provide these)
    leved081.py                   <- Level Editor (launched as its own process, untouched)
    vlak_pixel_painter_fixed.py   <- Texture Editor (launched as its own process, untouched)
"""

import os
import sys
import json
import glob
import shutil
import platform
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

FROZEN = bool(getattr(sys, "frozen", False))

# RES_DIR: read-only things bundled inside the program (tile images, fonts).
#   Frozen .exe -> PyInstaller's temp extraction folder. Source run -> script folder.
# APP_DIR: things the user owns and that must survive restarts (config, packs).
#   Frozen .exe -> the folder the .exe sits in. Source run -> script folder.
if FROZEN:
    RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    RES_DIR = APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = APP_DIR  # kept for backwards compatibility

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
METADATA_PATH = os.path.join(APP_DIR, "metadata.json")
SCN_DIR = os.path.join(APP_DIR, "scn")
PCX_DIR = os.path.join(APP_DIR, "pcx")
EXT_DIR = os.path.join(RES_DIR, "ext")
ASSETS_DIR = os.path.join(RES_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
WALL_TEXTURE_PATH = os.path.join(ASSETS_DIR, "wall.png")

LEVEL_EDITOR_SCRIPT = os.path.join(RES_DIR, "leved081.py")
TEXTURE_EDITOR_SCRIPT = os.path.join(RES_DIR, "vlak_pixel_painter_fixed.py")

# Flags used when the frozen .exe launches itself as one of the editors
FLAG_LEVEL_EDITOR = "--level-editor"
FLAG_TEXTURE_EDITOR = "--texture-editor"

TARGET_SCN_NAME = "VLAK$.SCN"
TARGET_PCX_NAME = "VLAK$.PCX"

# Colour palette - old 16-colour VGA feel: brick red, mortar/cream, near-black panels
COL_TITLEBAR = "#7a1010"
COL_TITLEBAR_TEXT = "#f4e6c1"
COL_PANEL_BG = "#1c1a17"
COL_BODY_BG = "#1c1a17"
COL_BUTTON_BG = "#7a2020"
COL_BUTTON_ACTIVE = "#9c2b2b"
COL_BUTTON_TEXT = "#f4e6c1"
COL_BORDER = "#4a1414"

COL_LOGO_MAIN = "#ffd23f"      # bright VGA yellow
COL_LOGO_OUTLINE = "#3a0d0d"   # dark brick shadow
COL_SUBTITLE = "#e8e8e8"

# Extra tones used to bring secondary windows (Settings, Packs) up to the
# same 1995-VGA look as the main window: recessed "LCD" fields, cream
# label text, and a brick-red selection highlight instead of Tk's default
# battleship gray / Windows blue.
COL_LABEL_TEXT = "#e8d9b0"     # warm parchment, slightly dimmer than titlebar text
COL_HEADER_TEXT = "#ffd23f"    # matches logo yellow, used for section headers
COL_FIELD_BG = "#100e0c"       # near-black recessed field background
COL_FIELD_TEXT = "#f4e6c1"
COL_FIELD_BORDER = "#4a1414"
COL_SELECT_BG = "#9c2b2b"      # brick-red selection instead of Windows blue
COL_SELECT_TEXT = "#f4e6c1"
COL_STATUS_TEXT = "#b8a888"

# Candidate font family names, in priority order. The first ones are true
# "IBM VGA" style bitmap-font recreations (freeware, e.g. from
# int10h.org's "Ultimate Oldschool PC Font Pack") - drop a .ttf/.otf for one
# of these into assets/fonts/ and it gets auto-registered at startup, no
# system install required. If none are found, we fall back to a plain
# monospace font so the launcher still looks reasonably retro.
PIXEL_FONT_CANDIDATES = [
    "Perfect DOS VGA 437", "Perfect DOS VGA 437 Win",
    "Px437 IBM VGA8", "Px437 IBM VGA9", "Px437 IBM VGA8 8x16",
    "IBM VGA 8x16", "IBM VGA9", "IBM VGA",
]
MONOSPACE_FALLBACKS = ["Consolas", "Courier New", "Courier", "monospace"]


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def register_bundled_fonts():
    """Privately register any .ttf/.otf files found in assets/fonts so they
    can be used without a system-wide install. Windows-only; a harmless
    no-op on other platforms or if the folder is empty."""
    if not os.path.isdir(FONTS_DIR):
        return
    font_files = glob.glob(os.path.join(FONTS_DIR, "*.ttf")) + \
        glob.glob(os.path.join(FONTS_DIR, "*.otf"))
    if not font_files or platform.system() != "Windows":
        return
    try:
        import ctypes
        FR_PRIVATE = 0x10
        for path in font_files:
            ctypes.windll.gdi32.AddFontResourceExW(path, FR_PRIVATE, 0)
    except Exception:
        pass


def pick_pixel_font(root, size, weight="normal"):
    """Return a (family, size, weight) tuple for the best available
    period-correct font, falling back gracefully."""
    available = set(tkfont.families(root))
    for name in PIXEL_FONT_CANDIDATES:
        if name in available:
            return (name, size, weight)
    for name in MONOSPACE_FALLBACKS:
        if name in available:
            return (name, size, weight)
    return ("Courier New", size, weight)


# ---------------------------------------------------------------------------
# Config / metadata helpers
# ---------------------------------------------------------------------------

def load_config():
    default = {"dosbox_path": "", "vlak_folder": ""}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_metadata():
    default = {"scn": {}, "pcx": {}}
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_metadata(metadata):
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def ensure_folders():
    for path in (SCN_DIR, PCX_DIR):
        os.makedirs(path, exist_ok=True)
    if FROZEN:
        # First run of the .exe: copy the sample packs that were bundled inside
        # it next to the .exe so the user can see/edit/add to them.
        for name in ("scn", "pcx"):
            bundled = os.path.join(RES_DIR, name)
            target = os.path.join(APP_DIR, name)
            if not os.path.isdir(bundled) or os.listdir(target):
                continue
            for fn in os.listdir(bundled):
                try:
                    shutil.copyfile(os.path.join(bundled, fn), os.path.join(target, fn))
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Reusable retro title bar (since we use overrideredirect for a custom look)
# ---------------------------------------------------------------------------

class RetroTitleBar(tk.Frame):
    """A fake title bar for a borderless (overrideredirect) window, with drag-to-move
    and a close button. Optionally shows a back/minimize style button too."""

    def __init__(self, parent, window, title, on_close=None, show_minimize=False, font=None):
        super().__init__(parent, bg=COL_TITLEBAR, height=28)
        self.window = window
        self.on_close_callback = on_close
        self._drag_x = 0
        self._drag_y = 0
        title_font = font or ("Segoe UI", 10, "bold")
        symbol_font = (title_font[0], max(title_font[1] - 1, 8), "bold")

        self.pack_propagate(False)

        label = tk.Label(self, text=title, bg=COL_TITLEBAR, fg=COL_TITLEBAR_TEXT,
                          font=title_font, anchor="w")
        label.pack(side=tk.LEFT, padx=10)

        close_btn = tk.Label(self, text="X", bg=COL_TITLEBAR, fg=COL_TITLEBAR_TEXT,
                              font=symbol_font, padx=12)
        close_btn.pack(side=tk.RIGHT, fill=tk.Y)
        close_btn.bind("<Button-1>", self._close)
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#c21c22"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=COL_TITLEBAR))

        if show_minimize:
            min_btn = tk.Label(self, text="_", bg=COL_TITLEBAR, fg=COL_TITLEBAR_TEXT,
                                font=symbol_font, padx=12)
            min_btn.pack(side=tk.RIGHT, fill=tk.Y)
            min_btn.bind("<Button-1>", lambda e: self.window.iconify())
            min_btn.bind("<Enter>", lambda e: min_btn.config(bg="#a50d12"))
            min_btn.bind("<Leave>", lambda e: min_btn.config(bg=COL_TITLEBAR))

        for widget in (self, label):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self.window.winfo_x() + (event.x - self._drag_x)
        y = self.window.winfo_y() + (event.y - self._drag_y)
        self.window.geometry(f"+{x}+{y}")

    def _close(self, event=None):
        if self.on_close_callback:
            self.on_close_callback()
        else:
            self.window.destroy()


def make_flat_button(parent, text, command, height=2, font=None):
    btn = tk.Button(
        parent, text=text.upper(), command=command,
        bg=COL_BUTTON_BG, activebackground=COL_BUTTON_ACTIVE,
        fg=COL_BUTTON_TEXT, activeforeground=COL_BUTTON_TEXT,
        relief="raised", bd=3, font=font or ("Courier New", 10, "bold"),
        height=height, cursor="hand2", highlightthickness=0
    )
    return btn


# ---------------------------------------------------------------------------
# Retro widget factories - used by secondary windows (Settings, Packs) so
# they share the same brick/parchment/VGA look as the main window instead
# of falling back to plain system-gray Tk widgets.
# ---------------------------------------------------------------------------

def make_retro_button(parent, text, command, font=None, width=None, small=False):
    """A compact raised-bevel button, styled like make_flat_button but
    sized for toolbars/dialogs (Browse..., Save, Cancel, Apply, etc.)."""
    btn = tk.Button(
        parent, text=text.upper() if small else text, command=command,
        bg=COL_BUTTON_BG, activebackground=COL_BUTTON_ACTIVE,
        fg=COL_BUTTON_TEXT, activeforeground=COL_BUTTON_TEXT,
        relief="raised", bd=2, font=font or ("Courier New", 9, "bold"),
        cursor="hand2", highlightthickness=0, padx=8, pady=3,
    )
    if width:
        btn.config(width=width)
    return btn


def make_retro_label(parent, text, font=None, header=False, bg=None):
    return tk.Label(
        parent, text=text, bg=bg or COL_BODY_BG,
        fg=COL_HEADER_TEXT if header else COL_LABEL_TEXT,
        font=font or ("Courier New", 9, "bold"), anchor="w",
    )


def make_retro_entry(parent, font=None, width=40):
    return tk.Entry(
        parent, width=width, bg=COL_FIELD_BG, fg=COL_FIELD_TEXT,
        insertbackground=COL_FIELD_TEXT, disabledbackground=COL_FIELD_BG,
        relief="sunken", bd=3, font=font or ("Courier New", 9),
        highlightthickness=1, highlightbackground=COL_FIELD_BORDER,
        highlightcolor=COL_FIELD_BORDER,
    )


def make_retro_listbox(parent, font=None, **kwargs):
    box = tk.Listbox(
        parent, bg=COL_FIELD_BG, fg=COL_FIELD_TEXT,
        selectbackground=COL_SELECT_BG, selectforeground=COL_SELECT_TEXT,
        relief="sunken", bd=3, font=font or ("Courier New", 9),
        highlightthickness=1, highlightbackground=COL_FIELD_BORDER,
        highlightcolor=COL_FIELD_BORDER, activestyle="none",
        **kwargs
    )
    return box


def make_retro_text(parent, font=None, height=5, width=30):
    return tk.Text(
        parent, height=height, width=width, wrap="word",
        bg=COL_FIELD_BG, fg=COL_FIELD_TEXT, insertbackground=COL_FIELD_TEXT,
        selectbackground=COL_SELECT_BG, selectforeground=COL_SELECT_TEXT,
        relief="sunken", bd=3, font=font or ("Courier New", 9),
        highlightthickness=1, highlightbackground=COL_FIELD_BORDER,
        highlightcolor=COL_FIELD_BORDER,
    )


def make_section_divider(parent, bg=None):
    """A thin dashed brick-red rule, echoing the one under the main logo."""
    canvas = tk.Canvas(parent, bg=bg or COL_BODY_BG, height=2,
                        highlightthickness=0)
    canvas.bind("<Configure>", lambda e: (
        canvas.delete("all"),
        canvas.create_line(0, 1, e.width, 1, fill=COL_TITLEBAR, dash=(4, 3), width=2)
    ))
    return canvas


# ---------------------------------------------------------------------------
# Main launcher window
# ---------------------------------------------------------------------------

class VlakLauncher:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.geometry("560x380+400+200")
        self.root.configure(bg=COL_BORDER)

        self.config_data = load_config()

        # Fonts - picks a bundled/installed IBM-VGA-style font if available,
        # otherwise falls back to a plain monospace face.
        self.font_titlebar = pick_pixel_font(root, 11, "bold")
        self.font_title = pick_pixel_font(root, 42, "bold")
        self.font_subtitle = pick_pixel_font(root, 16, "bold")
        self.font_button = pick_pixel_font(root, 11, "bold")

        self._wall_tile_img = None
        if PIL_AVAILABLE and os.path.exists(WALL_TEXTURE_PATH):
            try:
                self._wall_tile_img = Image.open(WALL_TEXTURE_PATH).convert("RGB")
            except Exception:
                self._wall_tile_img = None
        self._bg_photo = None  # keep a reference so Tk doesn't garbage-collect it

        outer = tk.Frame(root, bg=COL_BORDER, bd=1)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        RetroTitleBar(outer, root, "VLAK LAUNCHER", on_close=root.destroy,
                      show_minimize=True, font=self.font_titlebar).pack(fill=tk.X)

        # Logo / branding area
        logo_frame = tk.Frame(outer, bg=COL_BODY_BG, height=220)
        logo_frame.pack(fill=tk.BOTH, expand=True)
        logo_frame.pack_propagate(False)

        canvas = tk.Canvas(logo_frame, bg=COL_BODY_BG, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.bind("<Configure>", lambda e: self._draw_logo(canvas, e.width, e.height))

        # Button bar
        btn_bar = tk.Frame(outer, bg=COL_PANEL_BG, bd=0)
        btn_bar.pack(fill=tk.X)
        tk.Frame(btn_bar, bg=COL_BORDER, height=2).pack(fill=tk.X)

        buttons_row = tk.Frame(btn_bar, bg=COL_PANEL_BG)
        buttons_row.pack(fill=tk.X)

        buttons = [
            ("Play", self.on_play),
            ("Level Editor", self.on_level_editor),
            ("Texture Editor", self.on_texture_editor),
            ("Packs", self.on_packs),
            ("Settings", self.on_settings),
        ]
        for text, cmd in buttons:
            b = make_flat_button(buttons_row, text, cmd, font=self.font_button)
            b.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=8)

    def _tiled_background(self, width, height):
        """Build a PhotoImage of the wall texture tiled to fill width x height."""
        if not self._wall_tile_img or width <= 0 or height <= 0:
            return None
        tile = self._wall_tile_img
        tw, th = tile.size
        bg = Image.new("RGB", (width, height))
        for y in range(0, height, th):
            for x in range(0, width, tw):
                bg.paste(tile, (x, y))
        return ImageTk.PhotoImage(bg)

    def _draw_fallback_bricks(self, canvas, width, height):
        """Hand-drawn brick pattern used only if wall.png / Pillow aren't available."""
        brick_w, brick_h = 40, 18
        mortar = "#2a2320"
        brick_col = "#6b2222"
        canvas.create_rectangle(0, 0, width, height, fill=mortar, outline="")
        row = 0
        y = 0
        while y < height:
            offset = 0 if row % 2 == 0 else -brick_w // 2
            x = offset
            while x < width:
                canvas.create_rectangle(x + 1, y + 1, x + brick_w - 1, y + brick_h - 1,
                                         fill=brick_col, outline="")
                x += brick_w
            y += brick_h
            row += 1

    def _draw_outlined_text(self, canvas, x, y, text, font, fill, outline, offset=2):
        for dx in (-offset, 0, offset):
            for dy in (-offset, 0, offset):
                if dx == 0 and dy == 0:
                    continue
                canvas.create_text(x + dx, y + dy, text=text, font=font, fill=outline)
        canvas.create_text(x, y, text=text, font=font, fill=fill)

    def _draw_logo(self, canvas, width, height):
        canvas.delete("all")

        bg_photo = self._tiled_background(width, height)
        if bg_photo:
            self._bg_photo = bg_photo  # keep reference alive
            canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)
        else:
            self._draw_fallback_bricks(canvas, width, height)

        cx = width // 2

        # Dark plaque behind the text so it reads clearly over the brick texture
        canvas.create_rectangle(cx - 190, height // 2 - 62, cx + 190, height // 2 + 58,
                                 fill="#000000", outline="", stipple="gray50")

        self._draw_outlined_text(canvas, cx, height // 2 - 28, "VLAK",
                                  self.font_title, COL_LOGO_MAIN, COL_LOGO_OUTLINE)
        self._draw_outlined_text(canvas, cx, height // 2 + 30, "L A U N C H E R",
                                  self.font_subtitle, COL_SUBTITLE, COL_LOGO_OUTLINE, offset=1)

        canvas.create_line(30, height - 12, width - 30, height - 12,
                            fill=COL_TITLEBAR, dash=(4, 3), width=2)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_play(self):
        dosbox_path = self.config_data.get("dosbox_path", "")
        vlak_folder = self.config_data.get("vlak_folder", "")

        if not dosbox_path or not os.path.isfile(dosbox_path):
            messagebox.showerror(
                "Settings needed",
                "Your DOSBox.exe path isn't set correctly.\nOpen Settings and pick your DOSBox.exe first."
            )
            return
        if not vlak_folder or not os.path.isdir(vlak_folder):
            messagebox.showerror(
                "Settings needed",
                "Your VLAK folder isn't set correctly.\nOpen Settings and pick your VLAK installation folder first."
            )
            return

        args = [
            dosbox_path,
            "-c", f'mount c "{vlak_folder}"',
            "-c", "c:",
            "-c", "vlak.bat",
        ]
        try:
            subprocess.Popen(args, cwd=os.path.dirname(dosbox_path))
        except OSError as e:
            messagebox.showerror("Couldn't launch DOSBox", str(e))

    def on_level_editor(self):
        self._launch_script(LEVEL_EDITOR_SCRIPT, "Level Editor", FLAG_LEVEL_EDITOR)

    def on_texture_editor(self):
        self._launch_script(TEXTURE_EDITOR_SCRIPT, "Texture Editor", FLAG_TEXTURE_EDITOR)

    def _launch_script(self, script_path, friendly_name, flag):
        if FROZEN:
            # No Python on the user's PC: re-run this very .exe in "editor mode".
            args = [sys.executable, flag]
        else:
            if not os.path.isfile(script_path):
                messagebox.showerror(
                    "Missing file",
                    f"Couldn't find {os.path.basename(script_path)} next to the launcher."
                )
                return
            args = [sys.executable, script_path]
        try:
            subprocess.Popen(args, cwd=APP_DIR)
        except OSError as e:
            messagebox.showerror(f"Couldn't launch {friendly_name}", str(e))

    def on_packs(self):
        PacksWindow(self.root)

    def on_settings(self):
        SettingsWindow(self.root, self.config_data, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, new_config):
        self.config_data = new_config


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------

class SettingsWindow:
    def __init__(self, parent, config_data, on_saved=None):
        self.on_saved = on_saved
        self.config_data = dict(config_data)

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.geometry("480x260+450+260")
        self.win.configure(bg=COL_BORDER)
        self.win.grab_set()

        font_title = pick_pixel_font(self.win, 11, "bold")
        font_label = pick_pixel_font(self.win, 9, "bold")
        font_entry = pick_pixel_font(self.win, 9, "normal")
        font_button = pick_pixel_font(self.win, 9, "bold")

        outer = tk.Frame(self.win, bg=COL_BORDER, bd=1)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        RetroTitleBar(outer, self.win, "SETTINGS", on_close=self.win.destroy,
                      font=font_title).pack(fill=tk.X)
        make_section_divider(outer, bg=COL_PANEL_BG).pack(fill=tk.X)

        body = tk.Frame(outer, bg=COL_BODY_BG, padx=18, pady=18)
        body.pack(fill=tk.BOTH, expand=True)

        make_retro_label(body, "DOSBOX.EXE LOCATION:", font=font_label, header=True).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.dosbox_entry = make_retro_entry(body, font=font_entry, width=48)
        self.dosbox_entry.grid(row=1, column=0, sticky="we", padx=(0, 6))
        self.dosbox_entry.insert(0, self.config_data.get("dosbox_path", ""))
        make_retro_button(body, "Browse...", self.browse_dosbox, font=font_button).grid(
            row=1, column=1)

        make_retro_label(body, "VLAK GAME FOLDER:", font=font_label, header=True).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(18, 5))
        self.folder_entry = make_retro_entry(body, font=font_entry, width=48)
        self.folder_entry.grid(row=3, column=0, sticky="we", padx=(0, 6))
        self.folder_entry.insert(0, self.config_data.get("vlak_folder", ""))
        make_retro_button(body, "Browse...", self.browse_folder, font=font_button).grid(
            row=3, column=1)

        body.grid_columnconfigure(0, weight=1)

        btn_row = tk.Frame(body, bg=COL_BODY_BG)
        btn_row.grid(row=4, column=0, columnspan=2, pady=(28, 0), sticky="e")
        make_retro_button(btn_row, "Cancel", self.win.destroy, font=font_button,
                           width=10).pack(side=tk.RIGHT, padx=4)
        make_retro_button(btn_row, "Save", self.save, font=font_button,
                           width=10).pack(side=tk.RIGHT, padx=4)

    def browse_dosbox(self):
        path = filedialog.askopenfilename(
            title="Select DOSBox.exe",
            filetypes=[("DOSBox executable", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self.dosbox_entry.delete(0, tk.END)
            self.dosbox_entry.insert(0, path)

    def browse_folder(self):
        path = filedialog.askdirectory(title="Select your VLAK game folder")
        if path:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, path)

    def save(self):
        dosbox_path = self.dosbox_entry.get().strip()
        vlak_folder = self.folder_entry.get().strip()

        if dosbox_path and not os.path.isfile(dosbox_path):
            messagebox.showwarning("Check path", "That DOSBox.exe path doesn't seem to exist.")
            return
        if vlak_folder and not os.path.isdir(vlak_folder):
            messagebox.showwarning("Check path", "That VLAK folder doesn't seem to exist.")
            return

        new_config = {"dosbox_path": dosbox_path, "vlak_folder": vlak_folder}
        save_config(new_config)
        if self.on_saved:
            self.on_saved(new_config)
        self.win.destroy()


# ---------------------------------------------------------------------------
# Packs window (SCN / PCX selection)
# ---------------------------------------------------------------------------

class PacksWindow:
    def __init__(self, parent):
        self.config_data = load_config()
        self.metadata = load_metadata()

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.geometry("640x480+380+150")
        self.win.configure(bg=COL_BORDER)
        self.win.grab_set()

        font_title = pick_pixel_font(self.win, 11, "bold")
        font_header = pick_pixel_font(self.win, 10, "bold")
        font_label = pick_pixel_font(self.win, 9, "bold")
        font_list = pick_pixel_font(self.win, 9, "normal")
        font_button = pick_pixel_font(self.win, 9, "bold")

        outer = tk.Frame(self.win, bg=COL_BORDER, bd=1)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        RetroTitleBar(outer, self.win, "PACKS — CHOOSE YOUR SCN AND PCX",
                      on_close=self.win.destroy, font=font_title).pack(fill=tk.X)
        make_section_divider(outer, bg=COL_PANEL_BG).pack(fill=tk.X)

        body = tk.Frame(outer, bg=COL_BODY_BG, padx=14, pady=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # --- SCN column ---
        make_retro_label(body, "SCN:", font=font_header, header=True).grid(
            row=0, column=0, sticky="w")
        self.scn_listbox = make_retro_listbox(body, font=font_list, exportselection=False,
                                               selectmode=tk.SINGLE)
        self.scn_listbox.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.scn_listbox.bind("<<ListboxSelect>>", lambda e: self.show_info("scn"))

        scn_btns = tk.Frame(body, bg=COL_BODY_BG)
        scn_btns.grid(row=2, column=0, sticky="we", pady=6, padx=(0, 6))
        make_retro_button(scn_btns, "Import...", lambda: self.import_file("scn"),
                           font=font_button).pack(side=tk.LEFT)
        make_retro_button(scn_btns, "Remove", lambda: self.remove_file("scn"),
                           font=font_button).pack(side=tk.LEFT, padx=4)

        make_retro_label(body, "INFO:", font=font_label, header=True).grid(
            row=3, column=0, sticky="w", pady=(8, 4))
        self.scn_info = make_retro_text(body, font=font_list, height=5, width=30)
        self.scn_info.grid(row=4, column=0, sticky="nsew", padx=(0, 6))
        make_retro_button(body, "Save description", lambda: self.save_info("scn"),
                           font=font_button).grid(row=5, column=0, sticky="w", pady=6)

        # --- PCX column ---
        make_retro_label(body, "PCX:", font=font_header, header=True).grid(
            row=0, column=1, sticky="w")
        self.pcx_listbox = make_retro_listbox(body, font=font_list, exportselection=False,
                                               selectmode=tk.SINGLE)
        self.pcx_listbox.grid(row=1, column=1, sticky="nsew")
        self.pcx_listbox.bind("<<ListboxSelect>>", lambda e: self.show_info("pcx"))

        pcx_btns = tk.Frame(body, bg=COL_BODY_BG)
        pcx_btns.grid(row=2, column=1, sticky="we", pady=6)
        make_retro_button(pcx_btns, "Import...", lambda: self.import_file("pcx"),
                           font=font_button).pack(side=tk.LEFT)
        make_retro_button(pcx_btns, "Remove", lambda: self.remove_file("pcx"),
                           font=font_button).pack(side=tk.LEFT, padx=4)

        make_retro_label(body, "INFO:", font=font_label, header=True).grid(
            row=3, column=1, sticky="w", pady=(8, 4))
        self.pcx_info = make_retro_text(body, font=font_list, height=5, width=30)
        self.pcx_info.grid(row=4, column=1, sticky="nsew")
        make_retro_button(body, "Save description", lambda: self.save_info("pcx"),
                           font=font_button).grid(row=5, column=1, sticky="w", pady=6)

        # --- Apply bar ---
        make_section_divider(outer, bg=COL_PANEL_BG).pack(fill=tk.X)
        apply_bar = tk.Frame(outer, bg=COL_PANEL_BG)
        apply_bar.pack(fill=tk.X)
        self.status_label = tk.Label(apply_bar, text="", bg=COL_PANEL_BG, fg=COL_STATUS_TEXT,
                                      font=font_list, anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=10)
        make_retro_button(apply_bar, "Apply", self.apply_selection, font=font_button,
                           width=12).pack(side=tk.RIGHT, padx=10, pady=8)

        self.refresh_lists()

    # ------------------------------------------------------------------
    def refresh_lists(self):
        self.scn_listbox.delete(0, tk.END)
        for name in sorted(self._list_folder(SCN_DIR, ".scn")):
            self.scn_listbox.insert(tk.END, name)

        self.pcx_listbox.delete(0, tk.END)
        for name in sorted(self._list_folder(PCX_DIR, ".pcx")):
            self.pcx_listbox.insert(tk.END, name)

    @staticmethod
    def _list_folder(folder, extension):
        if not os.path.isdir(folder):
            return []
        return [f for f in os.listdir(folder) if f.lower().endswith(extension)]

    def _listbox_and_text(self, kind):
        if kind == "scn":
            return self.scn_listbox, self.scn_info
        return self.pcx_listbox, self.pcx_info

    def show_info(self, kind):
        listbox, text_widget = self._listbox_and_text(kind)
        selection = listbox.curselection()
        text_widget.delete("1.0", tk.END)
        if not selection:
            return
        name = listbox.get(selection[0])
        description = self.metadata.get(kind, {}).get(name, "")
        text_widget.insert("1.0", description)

    def save_info(self, kind):
        listbox, text_widget = self._listbox_and_text(kind)
        selection = listbox.curselection()
        if not selection:
            messagebox.showinfo("Nothing selected", f"Select a {kind.upper()} file first.")
            return
        name = listbox.get(selection[0])
        description = text_widget.get("1.0", tk.END).strip()
        self.metadata.setdefault(kind, {})[name] = description
        save_metadata(self.metadata)
        self.status_label.config(text=f"Saved description for {name}.")

    def import_file(self, kind):
        if kind == "scn":
            filetypes = [("SCN files", "*.scn"), ("All files", "*.*")]
            dest_dir = SCN_DIR
        else:
            filetypes = [("PCX files", "*.pcx"), ("All files", "*.*")]
            dest_dir = PCX_DIR

        path = filedialog.askopenfilename(title=f"Import {kind.upper()} file", filetypes=filetypes)
        if not path:
            return

        dest_name = os.path.basename(path)
        dest_path = os.path.join(dest_dir, dest_name)

        if os.path.exists(dest_path):
            if not messagebox.askyesno(
                "File already exists",
                f"'{dest_name}' already exists in your {kind.upper()} pack folder. Overwrite it?"
            ):
                return

        try:
            shutil.copyfile(path, dest_path)
        except OSError as e:
            messagebox.showerror("Import failed", str(e))
            return

        self.refresh_lists()
        self.status_label.config(text=f"Imported {dest_name}.")

    def remove_file(self, kind):
        listbox, text_widget = self._listbox_and_text(kind)
        selection = listbox.curselection()
        if not selection:
            messagebox.showinfo("Nothing selected", f"Select a {kind.upper()} file first.")
            return
        name = listbox.get(selection[0])
        if not messagebox.askyesno("Remove file", f"Remove '{name}' from your {kind.upper()} pack folder?\n"
                                                    "This deletes the file from disk."):
            return

        folder = SCN_DIR if kind == "scn" else PCX_DIR
        try:
            os.remove(os.path.join(folder, name))
        except OSError as e:
            messagebox.showerror("Couldn't remove file", str(e))
            return

        self.metadata.get(kind, {}).pop(name, None)
        save_metadata(self.metadata)
        text_widget.delete("1.0", tk.END)
        self.refresh_lists()
        self.status_label.config(text=f"Removed {name}.")

    def apply_selection(self):
        scn_selection = self.scn_listbox.curselection()
        pcx_selection = self.pcx_listbox.curselection()

        if not scn_selection or not pcx_selection:
            messagebox.showwarning("Pick both", "Select one SCN and one PCX file before applying.")
            return

        vlak_folder = self.config_data.get("vlak_folder", "")
        if not vlak_folder or not os.path.isdir(vlak_folder):
            messagebox.showerror("Settings needed", "Set your VLAK folder in Settings first.")
            return

        scn_name = self.scn_listbox.get(scn_selection[0])
        pcx_name = self.pcx_listbox.get(pcx_selection[0])

        scn_src = os.path.join(SCN_DIR, scn_name)
        pcx_src = os.path.join(PCX_DIR, pcx_name)
        scn_dst = os.path.join(vlak_folder, TARGET_SCN_NAME)
        pcx_dst = os.path.join(vlak_folder, TARGET_PCX_NAME)

        try:
            shutil.copyfile(scn_src, scn_dst)
            shutil.copyfile(pcx_src, pcx_dst)
        except OSError as e:
            messagebox.showerror("Apply failed", str(e))
            return

        messagebox.showinfo(
            "Applied",
            f"'{scn_name}' and '{pcx_name}' are now active as {TARGET_SCN_NAME} and {TARGET_PCX_NAME}."
        )
        self.status_label.config(text=f"Active: {scn_name} + {pcx_name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_editor_mode(flag):
    """Entry point used by the frozen .exe when the launcher starts an editor."""
    root = tk.Tk()
    if flag == FLAG_LEVEL_EDITOR:
        import leved081
        leved081.VlakEditor(root)
    else:
        import vlak_pixel_painter_fixed
        vlak_pixel_painter_fixed.PixelPainter(root)
    root.mainloop()


def main():
    if FLAG_LEVEL_EDITOR in sys.argv[1:]:
        return run_editor_mode(FLAG_LEVEL_EDITOR)
    if FLAG_TEXTURE_EDITOR in sys.argv[1:]:
        return run_editor_mode(FLAG_TEXTURE_EDITOR)
    ensure_folders()
    register_bundled_fonts()
    root = tk.Tk()
    root.withdraw()  # hide the default Tk window, we build our own chrome
    root.deiconify()
    VlakLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
