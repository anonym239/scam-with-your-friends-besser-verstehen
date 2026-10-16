"""NVIDIA-Grafikkarte für die Spracherkennung nutzen.

Die Spracherkennung (CTranslate2) bringt für die Grafikkarte nur einen kleinen Teil von NVIDIAs Bibliotheken mit.
Die großen Teile (cuBLAS und cuDNN, zusammen ~1,2 GB) lädt die Sprechhilfe auf Wunsch einmalig von NVIDIAs
offiziellen Paketen (PyPI) nach %APPDATA%\\Sprechhilfe\\cuda. Danach läuft alles offline.

Die Versionen sind fest: cuDNN 9.10.2.21 passt genau zu dem cudnn64_9.dll, den CTranslate2 4.8.3 mitbringt.
"""
import hashlib
import os
import shutil
import zipfile

from .config import data_dir

PACKAGES = [
    # (Name, Adresse, SHA-256, Größe in Bytes)
    ("cuBLAS 12.9",
     "https://files.pythonhosted.org/packages/45/a1/a17fade6567c57452cfc8f967a40d1035bb9301db52f27808167fbb2be2f/"
     "nvidia_cublas_cu12-12.9.1.4-py3-none-win_amd64.whl",
     "1e5fee10662e6e52bd71dec533fbbd4971bb70a5f24f3bc3793e5c2e9dc640bf", 553153899),
    ("cuDNN 9.10",
     "https://files.pythonhosted.org/packages/3d/90/0bd6e586701b3a890fd38aa71c387dab4883d619d6e5ad912ccbd05bfd67/"
     "nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl",
     "c6288de7d63e6cf62988f0923f96dc339cea362decb1bf5b3141883392a7d65e", 692992268),
]
_MARKER = "fertig.txt"
_MARKER_TEXT = "cublas 12.9.1.4, cudnn 9.10.2.21\n"


def cuda_dir():
    return os.path.join(data_dir(), "cuda")


def has_nvidia():
    """True, wenn eine NVIDIA-Grafikkarte mit Treiber da ist (braucht noch keine cuBLAS/cuDNN)."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def installed():
    try:
        with open(os.path.join(cuda_dir(), _MARKER), encoding="utf-8") as f:
            return f.read() == _MARKER_TEXT
    except OSError:
        return False


def activate():
    """Macht die nachgeladenen DLLs für Windows auffindbar. Muss vor dem Laden des Modells passieren."""
    folder = cuda_dir()
    if not installed():
        return False
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(folder)
        except OSError:
            pass
    if folder not in os.environ.get("PATH", ""):
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
    return True


def dll_members(names):
    """Aus der Dateiliste eines NVIDIA-Pakets die DLLs, die gebraucht werden (nvidia/<teil>/bin/*.dll)."""
    return [n for n in names if n.lower().endswith(".dll") and "/bin/" in n.replace("\\", "/")]


def install(progress=lambda text: None):
    """Lädt cuBLAS und cuDNN herunter, prüft sie und packt die DLLs aus. Wirft bei Fehlern eine Exception."""
    import requests

    folder = cuda_dir()
    os.makedirs(folder, exist_ok=True)
    need = sum(size for *_, size in PACKAGES) * 3
    if shutil.disk_usage(folder).free < need:
        raise OSError(f"Zu wenig Speicherplatz: Es werden etwa {need // 1_000_000_000 + 1} GB gebraucht.")
    total = sum(size for *_, size in PACKAGES)
    done_before = 0
    for name, url, sha256, size in PACKAGES:
        temp = os.path.join(folder, "download.tmp")
        digest = hashlib.sha256()
        loaded = 0
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(temp, "wb") as f:
                for chunk in response.iter_content(1 << 20):
                    f.write(chunk)
                    digest.update(chunk)
                    loaded += len(chunk)
                    percent = int((done_before + loaded) * 100 / total)
                    progress(f"Grafikkarte einrichten: {name} … {percent} %")
        if digest.hexdigest() != sha256:
            os.remove(temp)
            raise OSError(f"{name}: Download ist beschädigt, bitte nochmal versuchen.")
        progress(f"Grafikkarte einrichten: {name} wird ausgepackt …")
        with zipfile.ZipFile(temp) as archive:
            for member in dll_members(archive.namelist()):
                target = os.path.join(folder, os.path.basename(member))
                with archive.open(member) as source, open(target, "wb") as out:
                    shutil.copyfileobj(source, out, 1 << 20)
        os.remove(temp)
        done_before += size
    with open(os.path.join(folder, _MARKER), "w", encoding="utf-8") as f:
        f.write(_MARKER_TEXT)
    progress("Grafikkarte eingerichtet.")


def remove():
    shutil.rmtree(cuda_dir(), ignore_errors=True)
