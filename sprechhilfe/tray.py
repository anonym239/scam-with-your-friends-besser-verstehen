"""Das kleine Mikrofon-Symbol unten rechts in der Taskleiste (Infobereich). Farbe = Zustand, Rechtsklick = Menü."""
from PIL import Image, ImageDraw

COLORS = {
    "laden": (150, 150, 150),     # grau: Spracherkennung lädt
    "bereit": (40, 170, 90),      # grün: wartet auf die Sprechtaste
    "aufnahme": (220, 40, 40),    # rot: nimmt auf
    "erkennt": (60, 120, 230),    # blau: erkennt und tippt
    "pause": (230, 170, 30),      # gelb: Pause
    "fehler": (120, 0, 0),
}


def draw_icon(state):
    """Ein Mikrofon auf einem farbigen Kreis, 64×64."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.ellipse((1, 1, size - 2, size - 2), fill=COLORS.get(state, COLORS["laden"]) + (255,))
    white = (255, 255, 255, 255)
    d.rounded_rectangle((24, 10, 40, 38), radius=8, fill=white)          # Kapsel
    d.arc((16, 20, 48, 46), start=0, end=180, fill=white, width=4)       # Bügel
    d.line((32, 46, 32, 53), fill=white, width=4)                         # Stiel
    d.line((23, 54, 41, 54), fill=white, width=4)                         # Fuß
    if state == "pause":
        d.rectangle((44, 40, 48, 56), fill=(0, 0, 0, 255))
        d.rectangle((52, 40, 56, 56), fill=(0, 0, 0, 255))
    return image


class Tray:
    def __init__(self, on_pause, on_settings, on_log, on_mics, on_restart, on_quit, is_paused,
                 on_retype=lambda: None, on_forget_field=lambda: None, has_field=lambda: False,
                 on_setup_gpu=lambda: None, gpu_offer=lambda: False, key_items=()):
        import pystray
        self._pystray = pystray
        self.state = "laden"
        self.status = "Lade Spracherkennung …"
        self.last = ""
        item = pystray.MenuItem
        menu = pystray.Menu(
            item(lambda _: self.status, None, enabled=False),
            item(lambda _: f"Zuletzt: {self._short(self.last)}" if self.last else "Zuletzt: –", None, enabled=False),
            item("Letzten Satz nochmal tippen", lambda: on_retype(), enabled=lambda _: bool(self.last)),
            pystray.Menu.SEPARATOR,
            item("Pause", lambda: on_pause(), checked=lambda _: is_paused()),
            item("Tasten festlegen", pystray.Menu(*[
                item((lambda fn: lambda _: fn())(label), (lambda fn: lambda: fn())(action))
                for label, action in key_items])),
            item("Gemerktes Textfeld vergessen", lambda: on_forget_field(), visible=lambda _: has_field()),
            item("Grafikkarte einrichten (genauer und schneller)", lambda: on_setup_gpu(),
                 visible=lambda _: gpu_offer()),
            item("Einstellungen öffnen", lambda: on_settings()),
            item("Neu starten (Einstellungen übernehmen)", lambda: on_restart()),
            item("Was wurde verstanden? (Protokoll)", lambda: on_log()),
            item("Mikrofone anzeigen", lambda: on_mics()),
            pystray.Menu.SEPARATOR,
            item("Beenden", lambda: on_quit()),
        )
        self.icon = pystray.Icon("Sprechhilfe", draw_icon(self.state), "Sprechhilfe", menu)

    @staticmethod
    def _short(text, length=60):
        return text if len(text) <= length else text[:length - 1] + "…"

    def set(self, state=None, status=None, last=None):
        if state and state != self.state:
            self.state = state
            self.icon.icon = draw_icon(state)
        if status is not None:
            self.status = status
        if last is not None:
            self.last = last
        # Windows erlaubt höchstens 127 Zeichen im Tooltip.
        self.icon.title = self._short(f"Sprechhilfe: {self.status}", 120)
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, message):
        try:
            self.icon.notify(message, "Sprechhilfe")
        except Exception:
            pass

    def run(self, setup):
        self.icon.run(setup=lambda icon: (setattr(icon, "visible", True), setup()))

    def stop(self):
        self.icon.stop()
