# PyInstaller-Rezept. Baut zwei Varianten aus denselben Teilen:
#   dist\Sprechhilfe\Sprechhilfe.exe  (Ordner, für den Installer, startet am schnellsten)
#   dist\Sprechhilfe-EinKlick.exe     (eine einzige Datei: herunterladen, doppelklicken, fertig)
# Beide ohne Konsolenfenster: die Sprechhilfe läuft als Symbol unten rechts in der Taskleiste.
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries = [], []
hiddenimports = (collect_submodules("sprechhilfe") + collect_submodules("huggingface_hub") + collect_submodules("pystray")
                 + ["tqdm", "certifi", "requests", "charset_normalizer", "idna", "urllib3", "PIL.ImageDraw"])
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "huggingface_hub", "certifi",
                "sounddevice", "_sounddevice_data", "pystray"):
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

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Sprechhilfe", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Sprechhilfe", upx=False)

onefile = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="Sprechhilfe-EinKlick", console=False, upx=False,
              runtime_tmpdir=None)
