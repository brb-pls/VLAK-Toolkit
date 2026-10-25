# VLAK Toolkit

Launcher + **Level Editor** + **Sprayer Frayer** (PCX editor) for *VLAK 2.00* (Miroslav Němeček, 1995), in one program.
Everything is packed into a single **`VLAK-Toolkit.exe`** – **no Python needed**.

Based on:
- [VLAK-Level-Editor](https://github.com/brb-pls/VLAK-Level-Editor)
- [VLAK-Sprayer-Frayer](https://github.com/brb-pls/VLAK-Sprayer-Frayer)

## For users
1. Download `VLAK-Toolkit.exe` (or the `.zip`) from **Releases**.
2. Put it in its own folder and run it. On first start it creates `scn/`, `pcx/`, `config.json` next to the .exe.
3. **Settings** → point it at your `DOSBox.exe` and your VLAK folder → **Save** → **Play**.

The Level Editor and Texture Editor open from the launcher (they are the same .exe in a different mode).
`HLPGEN.EXE` (from the Sprayer Frayer repo) still has to sit in the same folder as the PCX you compress.

## For developers
Run from source: `pip install Pillow` then `python launcher.py`.

Build the .exe on Windows: `build.bat` → `dist\VLAK-Toolkit.exe`.

### Publishing a Release
```
git tag v1.0.0
git push origin v1.0.0
```
GitHub Actions (`.github/workflows/release.yml`) builds on Windows and attaches `VLAK-Toolkit.exe` + `.zip` to the Release.

### How the files are laid out
| Where | What |
|---|---|
| inside the .exe (read-only) | `ext/` tile images, `assets/` fonts + textures, the editor code |
| next to the .exe (yours) | `config.json`, `metadata.json`, `vlak_painter_config.txt`, `scn/`, `pcx/` |

## Licence
Pissware Licence (Revize 1) – see `LICENSE`.
