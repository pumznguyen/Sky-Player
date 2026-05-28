import shutil
import os
import time
from dataclasses import dataclass, field
from inputs import is_virtual_key_down, focusWindow
from scheduler import key_maps, VK_CODES

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_ENTER = 0x0D
VK_TAB = 0x09
VK_BACKSPACE = 0x08

PLAYBACK_FINISHED = "finished"
PLAYBACK_SKIPPED = "skipped"
PLAYBACK_QUIT = "quit"
PLAYBACK_POLL_SECONDS = 0.025
PROGRESS_RENDER_INTERVAL_SECONDS = 0.10

SPECIAL_HOTKEY_CODES = {
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "space": VK_SPACE,
    "enter": VK_ENTER,
    "return": VK_ENTER,
    "tab": VK_TAB,
    "backspace": VK_BACKSPACE,
}

VK_CODE_BY_KEY_NAME = {
    **VK_CODES,
    ";": 0xBA,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
}

@dataclass(frozen=True)
class HotkeyBinding:
    name: str
    key_code: int
    ctrl: bool = False
    alt: bool = False
    shift: bool = False

    @property
    def display(self):
        parts = []
        if self.ctrl:
            parts.append("Ctrl")
        if self.alt:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        parts.append(self.name.upper() if len(self.name) == 1 else self.name)
        return "+".join(parts)

    @property
    def has_modifier(self):
        return self.ctrl or self.alt or self.shift

@dataclass
class PlaybackControls:
    pause: HotkeyBinding
    skip: HotkeyBinding
    quit: HotkeyBinding
    refocus: HotkeyBinding
    enabled: bool = True
    _was_down: dict = field(default_factory=dict)

    def hint(self):
        if not self.enabled:
            return "hotkeys disabled"
        return (
            f"{self.pause.display} pause/resume | "
            f"{self.skip.display} skip | "
            f"{self.quit.display} quit | "
            f"{self.refocus.display} focus"
        )

    def poll(self):
        if not self.enabled:
            return None
        for action, hotkey in (
            ("quit", self.quit),
            ("skip", self.skip),
            ("pause", self.pause),
            ("refocus", self.refocus),
        ):
            is_down = is_hotkey_down(hotkey)
            was_down = self._was_down.get(action, False)
            self._was_down[action] = is_down
            if is_down and not was_down:
                return action
        return None

def is_hotkey_down(hotkey):
    if is_virtual_key_down(VK_CONTROL) != hotkey.ctrl:
        return False
    if is_virtual_key_down(VK_MENU) != hotkey.alt:
        return False
    if is_virtual_key_down(VK_SHIFT) != hotkey.shift:
        return False
    return is_virtual_key_down(hotkey.key_code)

def parse_hotkey(value):
    raw = value.strip()
    if not raw:
        raise ValueError("hotkey cannot be empty")

    tokens = [token.strip().casefold() for token in raw.replace("-", "+").split("+") if token.strip()]
    ctrl = False
    alt = False
    shift = False
    key_token = None

    for token in tokens:
        if token in {"ctrl", "control", "ctl"}:
            ctrl = True
        elif token == "alt":
            alt = True
        elif token == "shift":
            shift = True
        else:
            if key_token is not None:
                raise ValueError(f"invalid hotkey {value!r}: too many key tokens")
            key_token = token

    if key_token is None:
        raise ValueError(f"invalid hotkey {value!r}: missing key")

    if key_token.startswith("f") and key_token[1:].isdigit():
        index = int(key_token[1:])
        if 1 <= index <= 24:
            return HotkeyBinding(f"F{index}", 0x70 + index - 1, ctrl=ctrl, alt=alt, shift=shift)
        raise ValueError(f"unsupported function key: {key_token}")

    if key_token in SPECIAL_HOTKEY_CODES:
        display_name = "Esc" if key_token in {"esc", "escape"} else key_token.title()
        return HotkeyBinding(display_name, SPECIAL_HOTKEY_CODES[key_token], ctrl=ctrl, alt=alt, shift=shift)

    if len(key_token) == 1:
        key_code = VK_CODE_BY_KEY_NAME.get(key_token)
        if key_code is None and "a" <= key_token <= "z":
            key_code = ord(key_token.upper())
        if key_code is not None:
            return HotkeyBinding(key_token, key_code, ctrl=ctrl, alt=alt, shift=shift)

    raise ValueError(f"unsupported hotkey: {value!r}")

def hotkey_conflicts_with_note_keys(hotkey):
    if hotkey.has_modifier:
        return False
    return hotkey.name.casefold() in {mapped_key.casefold() for mapped_key in key_maps.values()}

def format_duration(seconds):
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{sec:02}"
    return f"{minutes}:{sec:02}"

def truncate_text(text, max_length):
    if max_length <= 0:
        return ""
    if len(text) <= max_length:
        return text
    if max_length == 1:
        return "…"
    return text[: max_length - 1] + "…"

class ProgressRenderer:
    def __init__(self, controls=None):
        self.controls = controls
        self.last_render_at = 0.0

    def render(self, current, total, song_name, status="playing", force=False):
        now = time.perf_counter()
        if not force and now - self.last_render_at < PROGRESS_RENDER_INTERVAL_SECONDS:
            return

        self.last_render_at = now
        terminal_width = shutil.get_terminal_size((100, 20)).columns
        total = max(total, 0.001)
        current = min(max(current, 0.0), total)
        fraction = current / total
        time_text = f"{format_duration(current)}/{format_duration(total)}"
        status_text = status.upper().replace("_", " ")
        controls_hint = self.controls.hint() if self.controls is not None else ""

        max_song_length = max(12, min(34, terminal_width // 3))
        song_label = truncate_text(song_name, max_song_length)
        hint = f" | {controls_hint}" if controls_hint else ""

        fixed_length = len(status_text) + len(song_label) + len(time_text) + len(hint) + 6
        bar_width = max(10, min(36, terminal_width - fixed_length))

        filled = min(bar_width, int(round(fraction * bar_width)))
        bar = "█" * filled + "░" * (bar_width - filled)
        line = f"{status_text:<10} {song_label} [{bar}] {time_text}{hint}"

        if len(line) > terminal_width:
            line = f"{status_text:<10} {song_label} [{bar}] {time_text}"
        if len(line) > terminal_width:
            overflow = len(line) - terminal_width
            song_label = truncate_text(song_label, max(8, len(song_label) - overflow - 1))
            line = f"{status_text:<10} {song_label} [{bar}] {time_text}"

        print("\r\033[K" + line, end="", flush=True)

    def finish(self, message):
        print("\r\033[K" + message, flush=True)

def progress_bar(current, total, song_name, replace_line, bar_length=40):
    renderer = ProgressRenderer()
    renderer.render(current, total, song_name, force=True)
    if current >= total:
        print("")

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')
