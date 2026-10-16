"""Tasten lesen (Sprechtaste) und Text ins Spiel tippen, direkt über die Windows-Schnittstelle (SendInput).

Tastennamen: "F8", "maus4", "strg+t". Mehrere Alternativen mit Komma: "F8, maus4".
"""
import ctypes
import sys
import time

IS_WINDOWS = sys.platform == "win32"

# Virtuelle Tastencodes (VK_*) für die Namen, die in der Einstellungsdatei stehen dürfen.
_NAMES = {
    "mauslinks": 0x01, "mausrechts": 0x02, "mausmitte": 0x04, "maus4": 0x05, "maus5": 0x06,
    "rueck": 0x08, "rück": 0x08, "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "eingabe": 0x0D, "return": 0x0D,
    "shift": 0x10, "umschalt": 0x10, "strg": 0x11, "ctrl": 0x11, "alt": 0x12, "pause": 0x13,
    "esc": 0x1B, "leertaste": 0x20, "leer": 0x20, "space": 0x20,
    "bildauf": 0x21, "bildab": 0x22, "ende": 0x23, "pos1": 0x24, "links": 0x25, "hoch": 0x26, "rechts": 0x27,
    "runter": 0x28, "einfg": 0x2D, "entf": 0x2E, "win": 0x5B,
    "num*": 0x6A, "num+": 0x6B, "num-": 0x6D, "num,": 0x6E, "num/": 0x6F,
    "rollen": 0x91, "lshift": 0xA0, "rshift": 0xA1, "lstrg": 0xA2, "rstrg": 0xA3, "lalt": 0xA4, "altgr": 0xA5,
    "ü": 0xBA, "+": 0xBB, "komma": 0xBC, ",": 0xBC, "-": 0xBD, ".": 0xBE, "#": 0xBF, "ö": 0xC0, "ß": 0xDB, "^": 0xDC,
    "´": 0xDD, "ä": 0xDE, "<": 0xE2,
}
_NAMES.update({f"f{i}": 0x6F + i for i in range(1, 25)})
_NAMES.update({f"num{i}": 0x60 + i for i in range(10)})
_NAMES.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})
_NAMES.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})

_MOUSE = {0x01, 0x02, 0x04, 0x05, 0x06}
# Tasten, die Windows als "erweitert" sendet (sonst kommen z. B. Pfeiltasten als Ziffernblock an).
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x6F, 0xA3, 0xA5}


class KeyError_(ValueError):
    pass


def parse_combo(text):
    """'strg+t' -> (0x11, 0x54). Wirft KeyError_ bei unbekannten Namen."""
    parts = [p.strip().lower() for p in text.replace(" + ", "+").split("+")]
    # "num+" oder eine einzelne "+"-Taste: das Plus gehört zum Namen.
    merged = []
    for part in parts:
        if part == "" and merged and merged[-1] == "num":
            merged[-1] = "num+"
        elif part == "":
            if not merged or merged[-1] != "+":
                merged.append("+")
        else:
            merged.append(part)
    if not merged:
        raise KeyError_("leer")
    codes = []
    for name in merged:
        if name in _NAMES:
            codes.append(_NAMES[name])
        elif name.startswith("vk") and name[2:].isdigit() and 0 < int(name[2:]) < 255:
            codes.append(int(name[2:]))     # jede andere Taste, z. B. Sondertasten von Gaming-Tastaturen
        else:
            raise KeyError_(name)
    return tuple(codes)


# Für die Anzeige und zum Speichern: ein Name pro Tastencode (der erste aus _NAMES, mit schöner Schreibweise).
_PRETTY = {"strg": "Strg", "alt": "Alt", "shift": "Shift", "leertaste": "Leertaste", "enter": "Enter", "esc": "Esc",
           "tab": "Tab", "maus4": "Maus4", "maus5": "Maus5", "mausmitte": "Mausmitte", "altgr": "AltGr"}
_VK_NAME = {}
for _name, _code in _NAMES.items():
    _VK_NAME.setdefault(_code, _name)
_VK_NAME.update({0x10: "shift", 0x11: "strg", 0x12: "alt", 0x0D: "enter", 0x20: "leertaste", 0x08: "rueck",
                0xBC: "komma"})


def key_name(code):
    name = _VK_NAME.get(code, f"vk{code}")
    if name in _PRETTY:
        return _PRETTY[name]
    if name.startswith("f") and name[1:].isdigit():
        return name.upper()
    return name


def combo_name(combo):
    return "+".join(key_name(code) for code in combo)


_MODIFIERS = (0x11, 0x12, 0x10, 0x5B)     # Strg, Alt, Shift, Win (in dieser Reihenfolge im Namen)
# Beim Abfragen überspringen: linke/rechte Maustaste (damit klickt man das Menü) und die Links/Rechts-Varianten
# von Shift/Strg/Alt (die allgemeinen Codes reichen und halten den Namen kurz).
_SKIP = {0x01, 0x02, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5C, 0xFF}


def capture_combo(is_down_fn=None, timeout=15.0, poll=0.01, cancel=0x1B):
    """Wartet, bis eine Taste (oder Maustaste 4/5/Mitte) gedrückt wird, und gibt die Kombination zurück.

    Gehaltene Strg/Alt/Shift/Win gehören dazu (z. B. Strg+F8). Nur eine Umschalttaste drücken und loslassen ergibt
    diese allein. Esc oder Zeitablauf -> None. Vorher wird gewartet, bis alle Tasten losgelassen sind.
    """
    down = is_down_fn or is_down
    codes = [c for c in range(1, 255) if c not in _SKIP]
    deadline = time.monotonic() + timeout
    while any(down(c) for c in codes):            # z. B. die Taste, mit der das Menü bedient wurde
        if time.monotonic() > deadline:
            return None
        time.sleep(poll)
    lone_modifier = None
    while time.monotonic() < deadline:
        pressed = [c for c in codes if down(c)]
        if cancel in pressed:
            return None
        main = [c for c in pressed if c not in _MODIFIERS]
        mods = [m for m in _MODIFIERS if m in pressed]
        if main:
            return tuple(mods) + (main[0],)
        if mods:
            lone_modifier = tuple(mods)
        elif lone_modifier:
            return lone_modifier                   # Umschalttaste allein gedrückt und losgelassen
        time.sleep(poll)
    return None


def parse_hotkeys(text):
    """'F8, maus4' -> [(0x77,), (0x05,)]. Leerer Text -> []."""
    return [parse_combo(part) for part in text.split(",") if part.strip()]


def is_mouse(combo):
    return any(code in _MOUSE for code in combo)


if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT
    _user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    _user32.MapVirtualKeyW.restype = wintypes.UINT
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _user32.OpenClipboard.argtypes = (wintypes.HWND,)
    _user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_EXTENDEDKEY = 0x01
    _KEYEVENTF_KEYUP = 0x02
    _KEYEVENTF_UNICODE = 0x04
    _KEYEVENTF_SCANCODE = 0x08

    def _send(events):
        array = (INPUT * len(events))(*events)
        return _user32.SendInput(len(events), array, ctypes.sizeof(INPUT))

    def _key_event(vk, up):
        scan = _user32.MapVirtualKeyW(vk, 0)
        flags = (_KEYEVENTF_KEYUP if up else 0) | (_KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0)
        if scan:
            # Mit Scancode: so kommt die Taste auch bei Spielen an, die "rohe" Tastatureingaben lesen.
            flags |= _KEYEVENTF_SCANCODE
        event = INPUT(type=_INPUT_KEYBOARD)
        event.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        return event

    def _char_events(unit):
        down = INPUT(type=_INPUT_KEYBOARD)
        down.ki = KEYBDINPUT(wVk=0, wScan=unit, dwFlags=_KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
        up = INPUT(type=_INPUT_KEYBOARD)
        up.ki = KEYBDINPUT(wVk=0, wScan=unit, dwFlags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        return [down, up]

    def is_down(vk):
        return bool(_user32.GetAsyncKeyState(vk) & 0x8000)

    def foreground_title():
        hwnd = _user32.GetForegroundWindow()
        buffer = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, buffer, 512)
        return buffer.value

    def press(combo):
        """Drückt eine Tastenkombination (z. B. strg+t): alle runter, dann rückwärts wieder hoch."""
        if not combo:
            return
        _send([_key_event(vk, False) for vk in combo])
        time.sleep(0.03)
        _send([_key_event(vk, True) for vk in reversed(combo)])

    def type_text(text, delay_ms=4):
        """Tippt Text als Unicode-Zeichen (Umlaute und ß inklusive), unabhängig vom Tastaturlayout."""
        data = text.encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        for unit in units:
            _send(_char_events(unit))
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)

    def set_clipboard(text):
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        data = (text + "\0").encode("utf-16-le")
        for _ in range(10):
            if _user32.OpenClipboard(None):
                break
            time.sleep(0.02)
        else:
            raise OSError("Zwischenablage ist belegt")
        try:
            _user32.EmptyClipboard()
            handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            pointer = _kernel32.GlobalLock(handle)
            ctypes.memmove(pointer, data, len(data))
            _kernel32.GlobalUnlock(handle)
            if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise OSError("Zwischenablage konnte nicht gesetzt werden")
        finally:
            _user32.CloseClipboard()

    def paste_text(text):
        set_clipboard(text)
        time.sleep(0.03)
        press((0x11, 0x56))  # Strg+V

    def set_console_title(title):
        _kernel32.SetConsoleTitleW(title)

    _user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    _user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    _user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    _user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    _user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    _INPUT_MOUSE = 0
    _MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

    def _client_rect(hwnd):
        rect = wintypes.RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(rect))
        origin = wintypes.POINT(0, 0)
        _user32.ClientToScreen(hwnd, ctypes.byref(origin))
        return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top

    def mouse_in_window():
        """Mausposition relativ zum Fenster vorne, als Anteil (0…1, 0…1), damit es auch bei anderer Auflösung passt."""
        hwnd = _user32.GetForegroundWindow()
        point = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        x, y, width, height = _client_rect(hwnd)
        if width <= 0 or height <= 0:
            return None
        return (point.x - x) / width, (point.y - y) / height

    def click_in_window(fx, fy):
        """Klickt an die gemerkte Stelle im Fenster vorne und stellt die Maus danach zurück."""
        hwnd = _user32.GetForegroundWindow()
        x, y, width, height = _client_rect(hwnd)
        if width <= 0 or height <= 0:
            return False
        old = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(old))
        _user32.SetCursorPos(int(x + fx * width), int(y + fy * height))
        time.sleep(0.03)
        events = []
        for flag in (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP):
            event = INPUT(type=_INPUT_MOUSE)
            event.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
            events.append(event)
        _send(events[:1])
        time.sleep(0.03)
        _send(events[1:])
        time.sleep(0.03)
        _user32.SetCursorPos(old.x, old.y)
        return True

else:  # Zum Entwickeln und Testen unter Linux/macOS: nichts drücken, nur so tun.
    def is_down(vk):
        return False

    def foreground_title():
        return ""

    def press(combo):
        pass

    def type_text(text, delay_ms=4):
        pass

    def paste_text(text):
        pass

    def set_console_title(title):
        pass

    def mouse_in_window():
        return None

    def click_in_window(fx, fy):
        return False


def any_down(hotkeys):
    """True, wenn eine der Alternativen komplett gedrückt ist."""
    return any(all(is_down(vk) for vk in combo) for combo in hotkeys)
