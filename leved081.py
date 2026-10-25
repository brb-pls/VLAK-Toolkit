import tkinter as tk
from tkinter import messagebox
import os
import sys

ROWS = 12
COLS = 20

# KOMPLETNÍ MAPOVÁNÍ PODLE SCN DEFINICE
TILESET = {
    ".": "empty", "#": "wall", "$": "train", "@": "gate",
    "A": "crystal", "B": "crown", "C": "tree", "D": "apple", 
    "E": "cow", "F": "cherries", "G": "pond", "H": "giraffe",
    "I": "icecream", "J": "cake", "K": "computer", "L": "car", 
    "M": "balloon", "N": "clock", "O": "elephant", "P": "wine",
    "Q": "money", "R": "plane", "S": "lemming", "T": "reserve"
}

ELEMENT_LABELS = {
    ".": "Nic", "#": "Zeď", "$": "Lokomotiva", "@": "Vrata",
    "A": "Krystal", "B": "Koruna", "C": "Strom", "D": "Jablko", 
    "E": "Kráva", "F": "Třešně", "G": "Rybník", "H": "Žirafa",
    "I": "Zmrzlina", "J": "Dort", "K": "Počítač", "L": "Auto", 
    "M": "Balón", "N": "Budík", "O": "Slon", "P": "Víno",
    "Q": "Peníze", "R": "Letadlo", "S": "Lemming", "T": "Rezerva (reserve)"
}

BG_MAIN = "#1e1e24"
BG_PANEL = "#25252b"
FG_TEXT = "#b0b0b5"
BG_BTN = "#2d2d35"        

class VlakEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("VLAK 2.00 - Level Editor [v0.81]")
        self.root.configure(bg=BG_MAIN)
        
        # Bezpečné načtení ikony (v .exe režimu z ext/train.png, jinak lokálně)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            panel_icon_path = os.path.join(sys._MEIPASS, "ext", "appletransparent.png")
        else:
            panel_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ext", "appletransparent.png")
            
        if os.path.exists(panel_icon_path):
            try:
                img_icon = tk.PhotoImage(file=panel_icon_path)
                # Použijeme standardní metodu, která v .exe zafunguje
                self.root.iconphoto(True, img_icon)
            except Exception:
                pass

        # Vynucení ID aplikace pro hlavní panel Windows (v .exe klíčové)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vlak.leveleditor.1.0")
        except Exception:
            pass
        self.root.title("VLAK 2.00 - Level Editor [v0.81]")
        self.root.configure(bg=BG_MAIN)
        
        self.current_element = tk.StringVar(value="#")
        self.macro_route = ""  
        
        self.pipeline_mode = False
        self.sim_train_pos = None     
        self.sim_snake = []           
        self.collected_items = 0      
        self.sim_grid_data = []  

        self.grid_data = [
            ["#" if r in (0, ROWS-1) or c in (0, COLS-1) else "." for c in range(COLS)]
            for r in range(ROWS)
        ]
            
        self.icons = {}
        self.load_tileset()

        self.buttons = {}
        self.create_widgets()

    def load_tileset(self):
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = sys._MEIPASS
        else:
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            except NameError:
                base_dir = os.path.abspath(".")
            
        ext_dir = os.path.join(base_dir, "ext")
        
        for spec, color in [("snake_head", "#4f4f5a"), ("snake_body", "#3e3e48")]:
            path = os.path.join(ext_dir, f"{spec}.png")
            if os.path.exists(path):
                try: self.icons[spec] = tk.PhotoImage(file=path)
                except Exception: pass
            
            if spec not in self.icons:
                img = tk.PhotoImage(width=32, height=32)
                img.put(color, to=(0, 0, 32, 32))
                self.icons[spec] = img

        for symbol, filename in TILESET.items():
            path = os.path.join(ext_dir, f"{filename}.png")
            if os.path.exists(path):
                try: 
                    self.icons[symbol] = tk.PhotoImage(file=path)
                except Exception: 
                    self.icons[symbol] = None

            if symbol not in self.icons or self.icons[symbol] is None:
                img = tk.PhotoImage(width=32, height=32)
                tile_color = "#35353e" if symbol == "#" else BG_BTN
                img.put(tile_color, to=(0, 0, 32, 32))
                self.icons[symbol] = img
                
        self.root._keep_alive = self.icons

    def create_widgets(self):
        top_frame = tk.Frame(self.root, bg=BG_MAIN, padx=15, pady=10)
        top_frame.pack(fill="x")
        
        tk.Label(top_frame, text="Heslo:", font=("Arial", 10, "bold"), bg=BG_MAIN, fg=FG_TEXT).pack(side="left")
        self.level_name = tk.Entry(top_frame, width=8, font=("Courier", 12, "bold"), bg=BG_PANEL, fg="#ffffff", bd=0, insertbackground="white", justify="center")
        self.level_name.insert(0, "LEVEL")
        self.level_name.pack(side="left", padx=5)

        tk.Label(top_frame, text="Číslo:", font=("Arial", 10, "bold"), bg=BG_MAIN, fg=FG_TEXT).pack(side="left", padx=(15, 0))
        self.level_number = tk.Entry(top_frame, width=4, font=("Courier", 12, "bold"), bg=BG_PANEL, fg="#ffffff", bd=0, insertbackground="white", justify="center")
        self.level_number.insert(0, "1")
        self.level_number.pack(side="left", padx=5)

        self.status_label = tk.Label(top_frame, text="Režim: Stavba", font=("Arial", 10, "bold"), bg="#3a3a45", fg=FG_TEXT, padx=8)
        self.status_label.pack(side="left", padx=20)

        self.macro_label = tk.Label(top_frame, text="Makro: S", font=("Courier", 10), bg=BG_MAIN, fg="#ffffff", anchor="w")
        self.macro_label.pack(side="left", fill="x", expand=True, padx=10)

        palette_container = tk.LabelFrame(self.root, text=" Paleta: ", font=("Arial", 9, "bold"), bg=BG_PANEL, fg=FG_TEXT, padx=5, pady=5, bd=1, relief="solid")
        palette_container.pack(side="left", fill="y", padx=15, pady=10)

        canvas = tk.Canvas(palette_container, bg=BG_PANEL, bd=0, highlightthickness=0, width=180)
        scrollbar = tk.Scrollbar(palette_container, orient="vertical", command=canvas.yview)
        self.palette_frame = tk.Frame(canvas, bg=BG_PANEL)

        self.palette_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.palette_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        for symbol, name in ELEMENT_LABELS.items():
            rb = tk.Radiobutton(self.palette_frame, text=f"  {name}", variable=self.current_element, value=symbol, 
                                anchor="w", bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_MAIN, font=("Arial", 9),
                                activebackground=BG_PANEL, activeforeground=FG_TEXT,
                                image=self.icons[symbol], compound="left")
            rb.pack(fill="x", pady=1)

        main_frame = tk.Frame(self.root, bg=BG_MAIN, pady=5, padx=10)
        main_frame.pack(side="right", fill="both", expand=True)

        self.grid_frame = tk.Frame(main_frame, bg=BG_MAIN)
        self.grid_frame.pack()

        for r in range(ROWS):
            for c in range(COLS):
                btn = tk.Button(self.grid_frame, bd=0, relief="flat", bg=BG_BTN, width=32, height=32,
                                highlightthickness=0, activebackground=BG_BTN)
                btn.grid(row=r, column=c, padx=0, pady=0)
                
                btn.config(command=lambda row=r, col=c: self.cell_clicked(row, col))
                self.buttons[(r, c)] = btn
        
        self.grid_frame.bind("<B1-Motion>", self.handle_mouse_drag)
        
        self.root.bind("<Up>", lambda e: self.handle_arrow_move("U"))
        self.root.bind("<Down>", lambda e: self.handle_arrow_move("D"))
        self.root.bind("<Left>", lambda e: self.handle_arrow_move("L"))
        self.root.bind("<Right>", lambda e: self.handle_arrow_move("R"))
        
        self.refresh_grid_display()

        pipeline_bar = tk.Frame(main_frame, bg=BG_PANEL, pady=5, padx=5)
        pipeline_bar.pack(fill="x", pady=5)

        self.pipeline_btn = tk.Button(pipeline_bar, text="REŽIM: Trasa (Šipky / Myš)", font=("Arial", 10, "bold"), bg="#42424a", fg=FG_TEXT, bd=0, pady=6, command=self.toggle_pipeline_mode)
        self.pipeline_btn.pack(side="left", padx=5)

        self.reset_pipeline_btn = tk.Button(pipeline_bar, text="Smazat trasu", font=("Arial", 10, "bold"), bg="#553535", fg=FG_TEXT, bd=0, pady=6, command=self.reset_pipeline, state="disabled")
        self.reset_pipeline_btn.pack(side="left", padx=5)

        btn_frame = tk.Frame(main_frame, bg=BG_MAIN, pady=5)
        btn_frame.pack(fill="x")

        tk.Button(btn_frame, text="Import ze schránky", font=("Arial", 11, "bold"), bg="#354555", fg=FG_TEXT, bd=0, pady=8, command=self.import_from_clipboard).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(btn_frame, text="Export do schránky", font=("Arial", 11, "bold"), bg="#35553b", fg=FG_TEXT, bd=0, pady=8, command=self.export_to_clipboard).pack(side="right", fill="x", expand=True, padx=5)

    def handle_mouse_drag(self, event):
        if self.pipeline_mode:
            return
        widget = event.widget.winfo_containing(event.x_root, event.y_root)
        for (r, c), btn in self.buttons.items():
            if btn == widget:
                self.cell_clicked(r, c)
                break

    def cell_clicked(self, r, c):
        if self.pipeline_mode:
            self.handle_pipeline_click(r, c)
            return

        new_symbol = self.current_element.get()
        if self.grid_data[r][c] == new_symbol:
            return

        if new_symbol in ["$", "@"]:
            for row in range(ROWS):
                for col in range(COLS):
                    if self.grid_data[row][col] == new_symbol:
                        self.grid_data[row][col] = "."
                        self.update_cell_view(row, col)

        self.grid_data[r][c] = new_symbol
        self.update_cell_view(r, c)

    def handle_arrow_move(self, direction):
        if not self.pipeline_mode or not self.sim_train_pos:
            return

        curr_r, curr_c = self.sim_train_pos
        
        if direction == "U": target_r, target_c = curr_r - 1, curr_c
        elif direction == "D": target_r, target_c = curr_r + 1, curr_c
        elif direction == "L": target_r, target_c = curr_r, curr_c - 1
        elif direction == "R": target_r, target_c = curr_r, curr_c + 1
        
        if 0 <= target_r < ROWS and 0 <= target_c < COLS:
            self.handle_pipeline_click(target_r, target_c)
        else:
            self.flash_error(curr_r, curr_c)

    def handle_pipeline_click(self, r, c):
        curr_r, curr_c = self.sim_train_pos
        dr, dc = r - curr_r, c - curr_c
        
        if (abs(dr) == 1 and dc == 0) or (abs(dc) == 1 and dr == 0):
            if dr == -1: direction = "U"
            elif dr == 1: direction = "D"
            elif dc == -1: direction = "L"
            else: direction = "R"

            if self.sim_grid_data[r][c] == "#":
                self.flash_error(r, c)
                return

            max_snake_len = self.collected_items + 1
            active_tail = self.sim_snake[:max_snake_len]
            if (r, c) in active_tail:
                if not ((r, c) == active_tail[-1] and not self.just_eaten_last_step):
                    self.flash_error(r, c)
                    return

            self.just_eaten_last_step = False
            target_cell = self.sim_grid_data[r][c]
            if target_cell not in [".", "$", "@"]:
                self.collected_items += 1
                self.just_eaten_last_step = True
                self.sim_grid_data[r][c] = "." 

            self.macro_route += direction
            self.sim_train_pos = (r, c)
            self.sim_snake.insert(0, (r, c))
            
            self.macro_label.config(text=f"Makro: {self.macro_route}S")
            self.refresh_grid_display()
        else:
            self.flash_error(r, c)

    def flash_error(self, r, c):
        self.buttons[(r, c)].config(bg="#6e2d35")
        self.root.after(150, lambda: self.buttons[(r, c)].config(bg=BG_BTN))

    def toggle_pipeline_mode(self):
        if not self.pipeline_mode:
            flat_grid = [cell for row in self.grid_data for cell in row]
            
            # STRIKTNÍ POJISTKA PRO MAKRO: Musí být Lokomotiva i Vrata
            if "$" not in flat_grid or "@" not in flat_grid:
                messagebox.showwarning("Chyba validace", "Nelze kreslit trasu! Na mapě musí být umístěna Lokomotiva ($) i Vrata (@).")
                return
                
            start_pos = next(((r, c) for r in range(ROWS) for c in range(COLS) if self.grid_data[r][c] == "$"), None)
            
            self.pipeline_mode = True
            self.sim_grid_data = [row[:] for row in self.grid_data]
            self.sim_train_pos = start_pos
            self.sim_snake = [start_pos]
            self.collected_items = 0
            self.just_eaten_last_step = False
            self.macro_route = ""
            
            self.status_label.config(text="REŽIM: Trasa", bg="#4a355c", fg="#ffffff")
            self.pipeline_btn.config(text="🛑 Ukončit trasu & Uložit", bg="#35553b", fg="#ffffff")
            self.reset_pipeline_btn.config(state="normal")
        else:
            self.pipeline_mode = False
            self.status_label.config(text="REŽIM: Stavba", bg="#3a3a45", fg=FG_TEXT)
            self.pipeline_btn.config(text="🚀 REŽIM: Kreslení trasy (Šipky / Myš)", bg="#42424a", fg=FG_TEXT)
            self.reset_pipeline_btn.config(state="disabled")
            
        self.refresh_grid_display()

    def reset_pipeline(self):
        self.macro_route = ""
        self.macro_label.config(text="Makro: S")
        if self.pipeline_mode:
            self.toggle_pipeline_mode()

    def update_cell_view(self, r, c, source_grid=None):
        if source_grid is None:
            source_grid = self.grid_data
        symbol = source_grid[r][c]
        self.buttons[(r, c)].config(image=self.icons[symbol])

    def refresh_grid_display(self):
        current_source = self.sim_grid_data if self.pipeline_mode else self.grid_data
        for r in range(ROWS):
            for c in range(COLS):
                self.update_cell_view(r, c, current_source)
        
        if self.pipeline_mode:
            max_snake_len = self.collected_items + 1
            for index, (sr, sc) in enumerate(self.sim_snake[:max_snake_len]):
                icon_key = "snake_head" if index == 0 else "snake_body"
                self.buttons[(sr, sc)].config(image=self.icons[icon_key])

    def import_from_clipboard(self):
        try: 
            text = self.root.clipboard_get()
        except tk.TclError: 
            return
        
        raw_lines = [line.strip() for line in text.split('\n') if line.strip()]
        map_lines = []
        possible_name = "HESLO"
        possible_num = "1"
        loaded_macro = "S"

        for line in raw_lines:
            if line.startswith(';'): 
                if "Level" in line or "Číslo" in line:
                    parts = line.split()
                    for p in parts:
                        if p.isdigit(): possible_num = p
                continue
            if line.startswith('!'):
                loaded_macro = line.replace('!', '').strip()
                continue
            if len(line) == 5 and line.isupper():
                possible_name = line
                continue
            if len(line) == 20: 
                map_lines.append(line)

        if len(map_lines) != 12: 
            return

        for r in range(ROWS):
            for c in range(COLS):
                self.grid_data[r][c] = map_lines[r][c]
        
        self.level_name.delete(0, tk.END)
        self.level_name.insert(0, possible_name)
        
        self.level_number.delete(0, tk.END)
        self.level_number.insert(0, possible_num)
        
        self.macro_route = loaded_macro.rstrip('S')
        self.macro_label.config(text=f"Makro: {loaded_macro}")
        self.refresh_grid_display()

    def export_to_clipboard(self):
        name = self.level_name.get().upper().strip()
        num_str = self.level_number.get().strip()
        
        if not num_str.isdigit() or not (1 <= int(num_str) <= 50):
            messagebox.showwarning("Chyba", "Číslo levelu musí být celé číslo od 1 do 50!")
            return
            
        flat_grid = [cell for row in self.grid_data for cell in row]
        
        # STRIKTNÍ POJISTKA PRO EXPORT: Musí obsahovat obojí
        if len(name) != 5 or "$" not in flat_grid or "@" not in flat_grid:
            messagebox.showwarning("Chyba validace", "Nelze exportovat! Úroveň musí mít platné 5místné heslo a musí obsahovat Lokomotivu ($) i Vrata (@).")
            return

        macro_out = f"! {self.macro_route}S"
        lines = [f"; {num_str}:", name, macro_out]
        for r in range(ROWS):
            lines.append("".join(self.grid_data[r]))
        
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines) + "\n")
        messagebox.showinfo("Exportováno", f"Level {num_str} i vygenerovaná trasa uloženy do schránky!")

if __name__ == "__main__":
    root = tk.Tk()
    app = VlakEditor(root)
    root.mainloop()
