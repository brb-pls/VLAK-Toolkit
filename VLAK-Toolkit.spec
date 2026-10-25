# PyInstaller spec - run:  pyinstaller VLAK-Toolkit.spec
# One .exe containing the launcher + Level Editor + Sprayer Frayer + all assets.
import os

datas = [
    ("ext", "ext"),
    ("assets", "assets"),
    ("scn", "scn"),   # sample packs, copied next to the .exe on first run
    ("pcx", "pcx"),
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["leved081", "vlak_pixel_painter_fixed", "PIL.ImageTk", "PIL._imagingtk", "PIL._tkinter_finder"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="VLAK-Toolkit",
    console=False,                       # no black terminal window
    icon="vlak.ico" if os.path.exists("vlak.ico") else None,
    upx=False,                           # UPX makes antivirus false-positives worse
)
