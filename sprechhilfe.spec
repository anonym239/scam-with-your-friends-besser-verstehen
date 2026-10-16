# PyInstaller-Rezept für Sprechhilfe.exe (Ordner-Variante: startet schneller als eine Einzeldatei).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries = [], []
hiddenimports = collect_submodules("sprechhilfe") + collect_submodules("huggingface_hub") + ["tqdm", "certifi", "requests"]
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "huggingface_hub", "certifi",
                "sounddevice", "_sounddevice_data"):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(["launcher.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "matplotlib", "PySide6", "PyQt5", "PyQt6"])
pyz = PYZ(a.pure)
# console=True: das kleine Fenster zeigt, was verstanden und getippt wurde.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Sprechhilfe", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Sprechhilfe", upx=False)
