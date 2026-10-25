import os
import sys
import struct
import subprocess
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import math

# Config lives next to the .exe (or the script), NOT in the current folder, so it
# is found no matter how/where the editor was started.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
    _RES_DIR = getattr(sys, "_MEIPASS", _APP_DIR)
else:
    _APP_DIR = _RES_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(_APP_DIR, "vlak_painter_config.txt")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                return lines[0], lines[1]
    return "", ""


def save_config(dosbox_path, game_dir):
    with open(CONFIG_FILE, "w") as f:
        f.write(f"{dosbox_path}\n{game_dir}")


def run_dosbox_command(dosbox_path, game_dir, command_list):
    if not dosbox_path or not os.path.exists(dosbox_path):
        messagebox.showerror("Chyba!", "Cesta k DOSBox.exe není správná.\n\nPokud si myslíte, že jde o chybu, pošlete zdrojový soubor s touto chybovou hláškou na brb@memeware.net.\nDOSBox.PathWrong1")
        return False
    args = [dosbox_path, "-noconsole"]
    for cmd in command_list:
        args.extend(["-c", cmd])
    args.extend(["-c", "exit"])
    subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def rle_decompress(body, expected_len):
    out = bytearray()
    i = 0
    n = len(body)
    while len(out) < expected_len and i < n:
        b = body[i]
        if (b & 0xC0) == 0xC0:
            # run marker
            if i + 1 >= n:
                break
            count = b & 0x3F
            val = body[i + 1]
            out.extend([val] * count)
            i += 2
        else:
            out.append(b)
            i += 1
    if len(out) < expected_len:
        out.extend([0] * (expected_len - len(out)))
    return out


def rle_compress_row(row_bytes):
    out = bytearray()
    i = 0
    n = len(row_bytes)
    while i < n:
        run_val = row_bytes[i]
        run_len = 1
        while i + run_len < n and row_bytes[i + run_len] == run_val and run_len < 63:
            run_len += 1
        if run_len > 1 or run_val >= 192:
            out.append(0xC0 | run_len)
            out.append(run_val)
        else:
            out.append(run_val)
        i += run_len
    return out


def read_pcx(path):
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 128:
        raise ValueError("Soubor je moc malý.\n\nPokud si myslíte, že jde o chybu, pošlete zdrojový soubor s touto chybovou hláškou na brb@memeware.net.\nPCX.fileTooSmall3")

    header = bytearray(data[:128])
    encoding = header[2]
    bpp = header[3]
    xmin, ymin, xmax, ymax = struct.unpack('<4H', header[4:12])
    width = xmax - xmin + 1
    height = ymax - ymin + 1
    nplanes = header[65]
    bytes_per_line = struct.unpack('<H', header[66:68])[0]
    body = data[128:]

    if bpp == 1 and nplanes in (1, 2, 4, 8):
        min_bpl = (width + 7) // 8
        bytes_per_line = max(bytes_per_line, min_bpl)
        expected = bytes_per_line * nplanes * height
        raw = rle_decompress(body, expected) if encoding == 1 else bytearray(body[:expected])
        if len(raw) < expected:
            raw.extend([0] * (expected - len(raw)))

        pixels = [0] * (width * height)
        row_stride = bytes_per_line * nplanes
        for y in range(height):
            row = raw[y * row_stride:(y + 1) * row_stride]
            planes = [row[p * bytes_per_line:(p + 1) * bytes_per_line] for p in range(nplanes)]
            base = y * width
            for x in range(width):
                byte_idx = x // 8
                bit_idx = 7 - (x % 8)
                val = 0
                for p in range(nplanes):
                    bit = (planes[p][byte_idx] >> bit_idx) & 1
                    val |= (bit << p)
                pixels[base + x] = val

        palette = [(header[16 + i * 3], header[17 + i * 3], header[18 + i * 3]) for i in range(16)]

        return {
            "mode": "planar",
            "header": bytes(header),
            "width": width, "height": height,
            "nplanes": nplanes, "bpp": bpp,
            "bytes_per_line": bytes_per_line,
            "pixels": pixels,
            "palette": palette,
            "max_index": (1 << nplanes) - 1,
        }

    elif bpp == 8 and nplanes == 1:
        bytes_per_line = max(bytes_per_line, width)
        expected = bytes_per_line * height
        raw = rle_decompress(body, expected) if encoding == 1 else bytearray(body[:expected])
        pixels = [0] * (width * height)
        for y in range(height):
            row = raw[y * bytes_per_line: y * bytes_per_line + width]
            pixels[y * width:(y + 1) * width] = list(row)

        if len(data) >= 769 and data[-769] == 0x0C:
            pal_bytes = data[-768:]
        else:
            pal_bytes = bytes(768)
        palette = [(pal_bytes[i * 3], pal_bytes[i * 3 + 1], pal_bytes[i * 3 + 2]) for i in range(256)]

        return {
            "mode": "indexed8",
            "header": bytes(header),
            "width": width, "height": height,
            "nplanes": 1, "bpp": 8,
            "bytes_per_line": bytes_per_line,
            "pixels": pixels,
            "palette": palette,
            "max_index": 255,
        }

    else:
        raise ValueError(f"Nepodporované rozvržení PCX souboru: bpp={bpp}, planes={nplanes}")


def write_pcx(path, info):
    width, height = info["width"], info["height"]
    pixels = info["pixels"]
    header = bytearray(info["header"])

    # Update bounding box in header (xmin=0,ymin=0)
    xmin = 0
    ymin = 0
    xmax = max(0, width - 1)
    ymax = max(0, height - 1)
    header[4:12] = struct.pack('<4H', xmin, ymin, xmax, ymax)

    # Write file depending on original mode
    if info["mode"] == "planar":
        nplanes = info["nplanes"]
        # compute minimal bytes_per_line and store in header
        bytes_per_line = max(info.get("bytes_per_line", 0), (width + 7) // 8)
        header[3] = 1  # bits per pixel
        header[65] = nplanes
        header[66:68] = struct.pack('<H', bytes_per_line)

        # keep header palette (16 colors) in sync
        for i in range(16):
            r, g, b = info["palette"][i] if i < len(info["palette"]) else (0, 0, 0)
            header[16 + i * 3] = r
            header[17 + i * 3] = g
            header[18 + i * 3] = b

        body = bytearray()
        for y in range(height):
            row = pixels[y * width:(y + 1) * width]
            planes = [bytearray(bytes_per_line) for _ in range(nplanes)]
            for x, val in enumerate(row):
                byte_idx = x // 8
                bit_idx = 7 - (x % 8)
                for p in range(nplanes):
                    if (val >> p) & 1:
                        planes[p][byte_idx] |= (1 << bit_idx)
            row_bytes = bytearray()
            for p in range(nplanes):
                row_bytes.extend(planes[p])
            body.extend(rle_compress_row(row_bytes))

        with open(path, "wb") as f:
            f.write(bytes(header))
            f.write(bytes(body))

    elif info["mode"] == "indexed8":
        bytes_per_line = max(info.get("bytes_per_line", 0), width)
        header[3] = 8
        header[65] = 1
        header[66:68] = struct.pack('<H', bytes_per_line)

        body = bytearray()
        for y in range(height):
            row = list(pixels[y * width:(y + 1) * width])
            if len(row) < bytes_per_line:
                row.extend([0] * (bytes_per_line - len(row)))
            body.extend(rle_compress_row(bytearray(row)))

        flat_palette = bytearray()
        for rgb in info["palette"]:
            flat_palette.extend(rgb)
        while len(flat_palette) < 768:
            flat_palette.extend([0, 0, 0])

        with open(path, "wb") as f:
            f.write(bytes(header))
            f.write(bytes(body))
            f.write(b'\x0c')
            f.write(bytes(flat_palette))

    else:
        raise ValueError("Neznámý PCX režim zápisu.")


class PixelPainter:
    def __init__(self, root):
        self.root = root
        self.root.title("VLAK 2.00 - Sprayer Frayer [0.81]")

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vlak.sprayerfrayer.0.81")
        except Exception:
            pass

        panel_icon_path = os.path.join(_RES_DIR, "ext", "sprayerfrayer.png")
            
        if os.path.exists(panel_icon_path):
            try:
                img_icon = tk.PhotoImage(file=panel_icon_path)
                self.root.iconphoto(True, img_icon)
            except Exception:
                pass

        self.dosbox_path, self.game_dir = load_config()

        # Core image state
        self.pcx_info = None     # dict returned by read_pcx() - single source of truth
        self.image = None        # PIL "P" image, kept only for on-screen rendering
        self.palette_rgb = []
        self.pixel_size = 8
        self.current_index = 1
        self.file_path = None
        self.grid_enabled = True

        self.tool_mode = "PAINT"

        self.sel_start_x = None
        self.sel_start_y = None
        self.selection_box = None
        self.sel_rect_id = None
        self.selected_sub_image = None
        self.is_moving_selection = False

        self.pan_start_x = 0
        self.pan_start_y = 0

        self.control_panel = tk.Frame(root, bg="gray")
        self.control_panel.pack(side=tk.TOP, fill=tk.X)

        self.row1 = tk.Frame(self.control_panel, bg="gray")
        self.row1.pack(fill=tk.X, padx=5, pady=2)
        tk.Button(self.row1, text="Nastavení", command=self.prompt_for_paths).pack(side=tk.LEFT, padx=2)
        tk.Button(self.row1, text="Otevřít Rozbalený PCX Soubor", command=self.load_file).pack(side=tk.LEFT, padx=2)
        tk.Button(self.row1, text="Uložit PCX", command=self.save_file).pack(side=tk.LEFT, padx=2)

        self.grid_btn = tk.Button(self.row1, text="Grid: ON", command=self.toggle_grid, bg="lightyellow")
        self.grid_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(self.row1, text="Zoom In (+)", command=lambda: self.adjust_zoom(2)).pack(side=tk.LEFT, padx=2)
        tk.Button(self.row1, text="Zoom Out (-)", command=lambda: self.adjust_zoom(-2)).pack(side=tk.LEFT, padx=2)

        self.paint_btn = tk.Button(self.row1, text="Režim: Kreslení", command=lambda: self.set_tool_mode("PAINT"), bg="darkgray", fg="white")
        self.paint_btn.pack(side=tk.LEFT, padx=10)
        self.select_btn = tk.Button(self.row1, text="Režim: Výběr", command=lambda: self.set_tool_mode("SELECT"), bg="lightgray")
        self.select_btn.pack(side=tk.LEFT, padx=2)

        self.color_indicator = tk.Label(self.row1, text="Index: 1", bg="#FFFFFF", width=12, relief="sunken")
        self.color_indicator.pack(side=tk.RIGHT, padx=5)

        self.row2 = tk.Frame(self.control_panel, bg="lightgray")
        self.row2.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(self.row2, text="Pack Cmd:", bg="lightgray").pack(side=tk.LEFT, padx=2)
        self.packer_entry = tk.Entry(self.row2, width=45)
        self.packer_entry.pack(side=tk.LEFT, padx=2)
        self.packer_entry.insert(0, "hlpgen.exe vlak.pcx vlak$.pcx")
        tk.Button(self.row2, text="Komprese (HLPGEN)", command=self.compress_assets, bg="lightgreen").pack(side=tk.LEFT, padx=5)

        self.workspace = tk.Frame(root)
        self.workspace.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        self.palette_frame = tk.Frame(self.workspace, width=140, bg="#333333")
        self.palette_frame.pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(self.palette_frame, text="Paleta", fg="white", bg="#333333").pack(pady=5)

        self.palette_canvas = tk.Canvas(self.palette_frame, width=120, bg="#333333", highlightthickness=0)
        self.palette_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas_container = tk.Frame(self.workspace, bg="black")
        self.canvas_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_container, bg="#222222", highlightthickness=0,
                                 xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)

        self.canvas.bind("<Button-3>", self.start_pan)
        self.canvas.bind("<B3-Motion>", self.pan_move)

        self.root.bind("<Delete>", self.delete_selection)
        self.root.bind("<Left>", lambda e: self.nudge_selection(-1, 0))
        self.root.bind("<Right>", lambda e: self.nudge_selection(1, 0))
        self.root.bind("<Up>", lambda e: self.nudge_selection(0, -1))
        self.root.bind("<Down>", lambda e: self.nudge_selection(0, 1))

        if not self.dosbox_path or not self.game_dir:
            self.root.after(100, self.prompt_for_paths)

    def prompt_for_paths(self):
        setup_win = tk.Toplevel(self.root)
        setup_win.title("Nastavte prosím cesty v systému:")
        setup_win.geometry("450x180")
        setup_win.grab_set()
        tk.Label(setup_win, text="DOSBox.exe Instalace:").pack(anchor=tk.W, padx=10, pady=2)
        db_frame = tk.Frame(setup_win)
        db_frame.pack(fill=tk.X, padx=10)
        db_entry = tk.Entry(db_frame)
        db_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        db_entry.insert(0, self.dosbox_path)

        def browse_dosbox():
            path = filedialog.askopenfilename(filetypes=[("Executables", "*.exe")])
            if path:
                db_entry.delete(0, tk.END)
                db_entry.insert(0, path)

        tk.Button(db_frame, text="Procházet...", command=browse_dosbox).pack(side=tk.RIGHT, padx=5)
        tk.Label(setup_win, text="VLAK Instalace:").pack(anchor=tk.W, padx=10, pady=2)
        gd_frame = tk.Frame(setup_win)
        gd_frame.pack(fill=tk.X, padx=10)
        gd_entry = tk.Entry(gd_frame)
        gd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        gd_entry.insert(0, self.game_dir)

        def browse_game_dir():
            path = filedialog.askdirectory()
            if path:
                gd_entry.delete(0, tk.END)
                gd_entry.insert(0, path)

        tk.Button(gd_frame, text="Procházet...", command=browse_game_dir).pack(side=tk.RIGHT, padx=5)

        def save_and_close():
            self.dosbox_path = db_entry.get()
            self.game_dir = gd_entry.get()
            save_config(self.dosbox_path, self.game_dir)
            setup_win.destroy()

        tk.Button(setup_win, text="Uložit nastavení", command=save_and_close, bg="lightgreen").pack(pady=15)

    def set_tool_mode(self, mode):
        self.tool_mode = mode
        if mode == "PAINT":
            self.paint_btn.config(bg="darkgray", fg="white")
            self.select_btn.config(bg="lightgray", fg="black")
            self.clear_selection_box()
        else:
            self.select_btn.config(bg="darkgray", fg="white")
            self.paint_btn.config(bg="lightgray", fg="black")

    def toggle_grid(self):
        self.grid_enabled = not self.grid_enabled
        self.grid_btn.config(text="Grid: ZAP." if self.grid_enabled else "Grid: VYP.")
        self.update_canvas()

    def adjust_zoom(self, delta):
        new_zoom = self.pixel_size + delta
        if 2 <= new_zoom <= 32:
            self.pixel_size = new_zoom
            self.update_canvas()

    def load_file(self):
        initial_dir = self.game_dir if self.game_dir else os.getcwd()
        self.file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=[("PCX files", "*.pcx")])
        if not self.file_path:
            return

        file_name = os.path.basename(self.file_path)

        try:
            self.pcx_info = read_pcx(self.file_path)
        except Exception as e:
            messagebox.showerror("Chyba formátu!", f"Soubor .PCX se nepodařilo zpracovat:\n{e} \n\nPokud si myslíte, že jde o chybu, pošlete zdrojový soubor s touto chybovou hláškou na brb@memeware.net.\nPCX.ParseNotFinished4")
            return

        self.palette_rgb = self.pcx_info["palette"]

        # Build a PIL "P" image purely for on-screen display/painting.
        self.image = Image.new("P", (self.pcx_info["width"], self.pcx_info["height"]))
        self.image.putdata(self.pcx_info["pixels"])
        flat_pal = []
        for rgb in self.palette_rgb:
            flat_pal.extend(rgb)
        flat_pal.extend([0, 0, 0] * (256 - len(self.palette_rgb)))
        self.image.putpalette(flat_pal[:768])

        self.build_palette_ui()
        self.set_active_color_index(1)
        self.update_canvas()

        base_no_ext, _ = os.path.splitext(file_name)
        out_name = "vlak$.pcx" if base_no_ext.lower() == "vlak" else f"{base_no_ext}$.pcx"
        self.packer_entry.delete(0, tk.END)
        self.packer_entry.insert(0, f"hlpgen.exe {file_name} {out_name}")

    def build_palette_ui(self):
        self.palette_canvas.delete("all")
        box_size, spacing, columns = 14, 2, 7
        for index, color in enumerate(self.palette_rgb):
            row, col = index // columns, index % columns
            x1 = col * (box_size + spacing) + spacing
            y1 = row * (box_size + spacing) + spacing
            hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            rect_id = self.palette_canvas.create_rectangle(x1, y1, x1 + box_size, y1 + box_size, fill=hex_color, outline="gray20")
            self.palette_canvas.tag_bind(rect_id, "<Button-1>", lambda e, idx=index: self.set_active_color_index(idx))
        self.palette_canvas.config(scrollregion=(0, 0, 120, (len(self.palette_rgb) // columns + 1) * (box_size + spacing)))

    def set_active_color_index(self, index):
        if not self.pcx_info:
            return
        if index < 0 or index > self.pcx_info["max_index"]:
            index = 0
        self.current_index = index
        color = self.palette_rgb[index]
        hex_str = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        self.color_indicator.config(text=f"Index: {index}", bg=hex_str, fg="white" if (color[0] + color[1] + color[2]) / 3 < 128 else "black")

    def update_canvas(self):
        if not self.image:
            return

        rgb_render = self.image.convert("RGB")
        w, h = rgb_render.size
        scaled_w, scaled_h = w * self.pixel_size, h * self.pixel_size

        self.display_img = rgb_render.resize((scaled_w, scaled_h), Image.NEAREST)
        self.tk_img = ImageTk.PhotoImage(self.display_img)
        self.canvas.config(scrollregion=(0, 0, scaled_w, scaled_h))
        self.canvas.delete("img", "grid")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img, tags="img")

        if self.grid_enabled:
            for x in range(0, scaled_w, self.pixel_size):
                self.canvas.create_line(x, 0, x, scaled_h, fill="#444444", tags="grid")
            for y in range(0, scaled_h, self.pixel_size):
                self.canvas.create_line(0, y, scaled_w, y, fill="#444444", tags="grid")
        self.draw_selection_box()

    def on_left_click(self, event):
        if self.tool_mode == "PAINT":
            self.paint(event)
        elif self.tool_mode == "SELECT":
            cx, cy = int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y))
            px, py = cx // self.pixel_size, cy // self.pixel_size
            if self.selection_box and (self.selection_box[0] <= px <= self.selection_box[2]) and (self.selection_box[1] <= py <= self.selection_box[3]):
                self.is_moving_selection = True
            else:
                self.is_moving_selection = False
                self.sel_start_x, self.sel_start_y = px, py
                self.clear_selection_box()

    def on_left_drag(self, event):
        if self.tool_mode == "PAINT":
            self.paint(event)
        elif self.tool_mode == "SELECT" and not self.is_moving_selection:
            cx, cy = int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y))
            px, py = cx // self.pixel_size, cy // self.pixel_size
            x1, x2 = min(self.sel_start_x, px), max(self.sel_start_x, px)
            y1, y2 = min(self.sel_start_y, py), max(self.sel_start_y, py)
            self.selection_box = [x1, y1, x2, y2]
            self.draw_selection_box()

    def on_left_release(self, event):
        if self.tool_mode == "SELECT" and self.selection_box:
            x1, y1, x2, y2 = self.selection_box
            if x2 >= x1 and y2 >= y1:
                self.selected_sub_image = self.image.crop((x1, y1, x2 + 1, y2 + 1))

    def paint(self, event):
        if not self.image:
            return
        if self.pcx_info and self.current_index > self.pcx_info["max_index"]:
            messagebox.showwarning(
                "Barva není dostupná!",
                f"Tento obrázek podporuje pouze indexy 0-{self.pcx_info['max_index']}.",
            )
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        img_x, img_y = int(cx // self.pixel_size), int(cy // self.pixel_size)
        if 0 <= img_x < self.image.width and 0 <= img_y < self.image.height:
            self.image.putpixel((img_x, img_y), self.current_index)
            self.update_canvas()

    def draw_selection_box(self):
        if self.sel_rect_id:
            self.canvas.delete(self.sel_rect_id)
        if not self.selection_box:
            return
        x1, y1, x2, y2 = self.selection_box
        cx1, cy1 = x1 * self.pixel_size, y1 * self.pixel_size
        cx2, cy2 = (x2 + 1) * self.pixel_size, (y2 + 1) * self.pixel_size
        self.sel_rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="cyan", width=2, dash=(4, 4))

    def clear_selection_box(self):
        self.selection_box = None
        self.selected_sub_image = None
        if self.sel_rect_id:
            self.canvas.delete(self.sel_rect_id)

    def delete_selection(self, event=None):
        if self.tool_mode != "SELECT" or not self.selection_box or not self.image:
            return
        x1, y1, x2, y2 = self.selection_box
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if 0 <= x < self.image.width and 0 <= y < self.image.height:
                    self.image.putpixel((x, y), 0)
        self.clear_selection_box()
        self.update_canvas()

    def nudge_selection(self, dx, dy):
        if self.tool_mode != "SELECT" or not self.selection_box or not self.selected_sub_image:
            return
        x1, y1, x2, y2 = self.selection_box

        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if 0 <= x < self.image.width and 0 <= y < self.image.height:
                    self.image.putpixel((x, y), 0)

        x1, x2 = x1 + dx, x2 + dx
        y1, y2 = y1 + dy, y2 + dy
        self.selection_box = [x1, y1, x2, y2]

        sub_w, sub_h = self.selected_sub_image.size
        for sx in range(sub_w):
            for sy in range(sub_h):
                target_x = x1 + sx
                target_y = y1 + sy
                if 0 <= target_x < self.image.width and 0 <= target_y < self.image.height:
                    idx_val = self.selected_sub_image.getpixel((sx, sy))
                    self.image.putpixel((target_x, target_y), idx_val)
        self.update_canvas()

    def start_pan(self, event):
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def pan_move(self, event):
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        dampening = 0.5
        scroll_x = int(dx * dampening)
        scroll_y = int(dy * dampening)
        if scroll_x != 0:
            self.canvas.xview_scroll(-scroll_x, "units")
            self.pan_start_x = event.x
        if scroll_y != 0:
            self.canvas.yview_scroll(-scroll_y, "units")
            self.pan_start_y = event.y

    def save_file(self):
        if not self.image or not self.file_path or not self.pcx_info:
            return

        # Pull edited pixel data back into pcx_info
        self.pcx_info["pixels"] = list(self.image.getdata())
        self.pcx_info["palette"] = self.palette_rgb

        try:
            write_pcx(self.file_path, self.pcx_info)
            messagebox.showinfo("Úspěch!", f"Změny byly uloženy v binárním formátu souboru: \n{os.path.basename(self.file_path)}")
        except Exception as e:
            messagebox.showerror("Chyba uložení!", f"Zápis binárního souboru se nezdařil: \n{str(e)} \n\nPokud si myslíte, že jde o chybu, pošlete zdrojový soubor s touto chybovou hláškou na brb@memeware.net.\nPCX.SaveFailed3")

    def compress_assets(self):
        if not self.file_path or not self.dosbox_path:
            messagebox.showwarning("Chybějící nastavení!", "Nejprve prosím otevřete nekomprimovaný soubor formátu PCX.")
            return

        # Ensure we save the latest edits before running HLPGEN
        self.save_file()

        target_working_dir = os.path.dirname(self.file_path)
        source_name = os.path.basename(self.file_path)
        cmd_string = self.packer_entry.get()

        candidates = ["hlpgen.exe", "hlpgen.com"]
        hlpgen_name = None
        on_disk_lower = {f.lower(): f for f in os.listdir(target_working_dir)} if os.path.isdir(target_working_dir) else {}
        for cand in candidates:
            if cand in on_disk_lower:
                hlpgen_name = on_disk_lower[cand]
                break

        if not hlpgen_name:
            messagebox.showerror(
                "Chybí nástroj!",
                f"HLPGEN.EXE nebyl nalezen v: \n{target_working_dir}\n\n"
                "Prosím, zkopíruj HLPGEN.EXE do tohoto adresáře, aby jej DOSBox mohl využívat!"
            )
            return

        if cmd_string.split() and cmd_string.split()[0].lower() in ("hlpgen.exe", "hlpgen.com") and cmd_string.split()[0] != hlpgen_name:
            tokens = cmd_string.split()
            tokens[0] = hlpgen_name
            cmd_string = " ".join(tokens)
            self.packer_entry.delete(0, tk.END)
            self.packer_entry.insert(0, cmd_string)

        # Sanity check referenced input exists (case-insensitive)
        cmd_tokens = cmd_string.split()
        if len(cmd_tokens) >= 2:
            referenced_input = cmd_tokens[1]
            if referenced_input.lower() not in on_disk_lower:
                messagebox.showwarning(
                    "Nesoulad s názvem souboru!",
                    f"Pack Cmd odkazuje na '{referenced_input}', ale žádný soubor s tímto "
                    f"jménem nebyl v tomto adresáři nalezen: \n{target_working_dir}\n\n"
                    f"Soubory, které se tam nacházejí (debug): {sorted(on_disk_lower.values())}\n\n"
                    "Uprav text příkazu Pack Cmd tak, aby odpovídal skutečnému názvu souboru, a zkus to znovu."
                )
                return

        base_no_ext, _ = os.path.splitext(source_name)
        expected_output_name = "vlak$.pcx" if base_no_ext.lower() == "vlak" else f"{base_no_ext}$.pcx"
        expected_full_path = os.path.join(target_working_dir, expected_output_name)

        # Backup previous output to avoid HLPGEN overwrite prompt
        if os.path.exists(expected_full_path):
            backup_path = expected_full_path + ".bak"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.replace(expected_full_path, backup_path)

        cmds = [
            f'mount c "{target_working_dir}"',
            "c:",
            cmd_string,
            "choice /N /T:C,2 > nul"
        ]

        run_dosbox_command(self.dosbox_path, target_working_dir, cmds)

        found = False
        for _ in range(10):
            if os.path.exists(expected_full_path):
                found = True
                break
            time.sleep(0.3)

        if found:
            messagebox.showinfo("Úspěch!", f"Komprimovaný PCX soubor byl vytvořen zde: \n{expected_full_path}")
        else:
            messagebox.showwarning(
                "Varování při spouštění!",
                f"DOSBox byl ukončen, ale '{expected_output_name}' nebyl v tomto adresáři nalezen:\n"
                f"{target_working_dir}\n\n"
                "Předchozí výstup (pokud nějaký vůbec byl) byl již před tímto spuštěním zapomenut, "
                "čili se nejedná o problém s přepisováním souboru. Zkontrolujte, zda příkaz Pack Cmd "
                "odpovídá syntaxi příkazu HLP: HLPGEN input_file output_file "
                "[/K|/L|/I|/B] [/G \"password\"]."
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = PixelPainter(root)
    root.mainloop()
