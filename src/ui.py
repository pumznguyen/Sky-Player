import shutil
import os
import time
from dataclasses import dataclass, field
from inputs import is_virtual_key_down, focusWindow
from sky_music.layouts import SKY_15_KEY_MAP as key_maps, VK_CODES

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
    def display(self) -> str:
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
    def has_modifier(self) -> bool:
        return self.ctrl or self.alt or self.shift

@dataclass
class PlaybackControls:
    pause: HotkeyBinding
    skip: HotkeyBinding
    quit: HotkeyBinding
    refocus: HotkeyBinding
    panic: HotkeyBinding
    enabled: bool = True
    _was_down: dict[str, bool] = field(default_factory=dict)

    def hint(self) -> str:
        if not self.enabled:
            return "hotkeys disabled"
        return (
            f"{self.pause.display} pause/resume | "
            f"{self.skip.display} skip | "
            f"{self.quit.display} quit | "
            f"{self.refocus.display} refocus Sky | "
            f"{self.panic.display} panic release"
        )

    def poll(self) -> str | None:
        if not self.enabled:
            return None
        for action, hotkey in (
            ("quit", self.quit),
            ("skip", self.skip),
            ("pause", self.pause),
            ("refocus", self.refocus),
            ("panic", self.panic),
        ):
            is_down = is_hotkey_down(hotkey)
            was_down = self._was_down.get(action, False)
            self._was_down[action] = is_down
            if is_down and not was_down:
                return action
        return None

def is_hotkey_down(hotkey: HotkeyBinding) -> bool:
    """Check if a hotkey is currently pressed.

    Required modifiers must be held; extra modifiers are ignored unless
    the hotkey itself has no modifiers (to avoid false positives with
    Ctrl+something accidentally triggering plain-key hotkeys).
    """
    ctrl_down = is_virtual_key_down(VK_CONTROL)
    alt_down = is_virtual_key_down(VK_MENU)
    shift_down = is_virtual_key_down(VK_SHIFT)

    # Required modifiers must be held
    if hotkey.ctrl and not ctrl_down:
        return False
    if hotkey.alt and not alt_down:
        return False
    if hotkey.shift and not shift_down:
        return False

    # For plain (no-modifier) hotkeys, require that no modifier is held
    # to prevent Ctrl+F8 accidentally triggering the plain F8 hotkey.
    if not hotkey.has_modifier:
        if ctrl_down or alt_down or shift_down:
            return False

    return is_virtual_key_down(hotkey.key_code)

def parse_hotkey(value: str) -> HotkeyBinding:
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

def hotkey_conflicts_with_note_keys(hotkey: HotkeyBinding) -> bool:
    if hotkey.has_modifier:
        return False
    return hotkey.name.casefold() in {mapped_key.casefold() for mapped_key in key_maps.values()}

def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{sec:02}"
    return f"{minutes}:{sec:02}"

def truncate_text(text: str, max_length: int) -> str:
    if max_length <= 0:
        return ""
    if len(text) <= max_length:
        return text
    if max_length == 1:
        return "…"
    return text[: max_length - 1] + "…"

class ProgressRenderer:
    def __init__(
        self,
        controls: PlaybackControls | None = None,
        verbose: bool = False,
        profile_name: str = "balanced",
        tempo_scale: float = 1.0,
    ) -> None:
        self.controls = controls
        self.verbose = verbose
        self.profile_name = profile_name
        self.tempo_scale = tempo_scale
        self.last_render_at: float = 0.0
        # Live timing counters updated by PlaybackEngine
        self.late_2ms: int = 0
        self.late_5ms: int = 0
        self.late_10ms: int = 0
        self.max_lateness_us: int = 0
        self._verbose_initialized: bool = False

    def update_counters(self, lateness_us: int) -> None:
        """Called by PlaybackEngine after each key action to update live timing counters."""
        if lateness_us > 10000:
            self.late_10ms += 1
            self.late_5ms += 1
            self.late_2ms += 1
        elif lateness_us > 5000:
            self.late_5ms += 1
            self.late_2ms += 1
        elif lateness_us > 2000:
            self.late_2ms += 1
        if lateness_us > self.max_lateness_us:
            self.max_lateness_us = lateness_us

    def render(self, current: float, total: float, song_name: str, status: str = "playing", force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_render_at < PROGRESS_RENDER_INTERVAL_SECONDS:
            return

        self.last_render_at = now
        terminal_width = shutil.get_terminal_size((100, 20)).columns
        total = max(total, 0.001)
        current = min(max(current, 0.0), total)
        fraction = current / total
        time_text = f"{format_duration(current)}/{format_duration(total)}"
        if status == "panic":
            status_text = "PANIC REL"
        else:
            status_text = status.upper().replace("_", " ")
        controls_hint = ""
        if status == "focus_lost" and self.controls is not None:
            controls_hint = f"Press {self.controls.refocus.display} to refocus Sky"

        max_song_length = max(12, min(34, terminal_width // 3))
        song_label = truncate_text(song_name, max_song_length)

        # Build profile/tempo suffix for compact and verbose modes
        profile_hint = f"{self.profile_name} {self.tempo_scale:.2f}x"

        if controls_hint:
            hint = f" | {controls_hint}"
        else:
            hint = ""

        fixed_length = len(status_text) + len(song_label) + len(time_text) + len(hint) + 6
        bar_width = max(10, min(36, terminal_width - fixed_length))

        filled = min(bar_width, int(round(fraction * bar_width)))
        bar = "█" * filled + "░" * (bar_width - filled)
        line1 = f"{status_text:<10} {song_label} [{bar}] {time_text}{hint}"

        # Try to append profile/tempo suffix if space allows (compact and verbose share this)
        line1_with_profile = f"{line1} | {profile_hint}"
        if len(line1_with_profile) <= terminal_width:
            line1 = line1_with_profile

        if len(line1) > terminal_width:
            line1 = f"{status_text:<10} {song_label} [{bar}] {time_text}"
        if len(line1) > terminal_width:
            overflow = len(line1) - terminal_width
            song_label = truncate_text(song_label, max(8, len(song_label) - overflow - 1))
            line1 = f"{status_text:<10} {song_label} [{bar}] {time_text}"

        if self.verbose:
            line2 = (
                f"           Late >2ms:{self.late_2ms} "
                f">5ms:{self.late_5ms} "
                f">10ms:{self.late_10ms}  "
                f"max:{self.max_lateness_us}\u00b5s"
            )
            if self._verbose_initialized:
                output = f"\033[1A\r\033[K{line1}\n\r\033[K{line2}"
            else:
                output = f"{line1}\n{line2}"
                self._verbose_initialized = True
            print(output, end="", flush=True)
        else:
            print("\r\033[K" + line1, end="", flush=True)

    def finish(self, message: str) -> None:
        if self.verbose and self._verbose_initialized:
            print(f"\033[1A\r\033[K\r\033[K" + message, flush=True)
        else:
            print("\r\033[K" + message, flush=True)

def clear_terminal() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
