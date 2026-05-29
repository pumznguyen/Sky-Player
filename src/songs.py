import json
import time
from pathlib import Path
from typing import Any
import inputs

SONG_DIR: Path = Path("songs")
SUPPORTED_EXTENSIONS: set[str] = {".json", ".skysheet"}
CONFIG_PATH: Path = Path("config.json")

def load_saved_theme() -> str:
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                theme = data.get("theme")
                if isinstance(theme, str):
                    return theme
        except Exception:
            pass
    return "aurora"

def save_theme(theme_name: str) -> None:
    try:
        data = {}
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["theme"] = theme_name
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

ACTIVE_THEME: str = load_saved_theme()

_song_choices_cache: list[Path] = []
_song_choices_mtime_ns: int | None = None

def load_song_choices() -> list[Path]:
    if not SONG_DIR.exists():
        return []
    return sorted(
        [path for path in SONG_DIR.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda path: path.name.lower(),
    )

def get_song_choices(force_refresh: bool = False) -> list[Path]:
    global _song_choices_cache, _song_choices_mtime_ns
    if not SONG_DIR.exists():
        _song_choices_cache = []
        _song_choices_mtime_ns = None
        return _song_choices_cache

    current_mtime_ns = SONG_DIR.stat().st_mtime_ns
    if force_refresh or _song_choices_mtime_ns != current_mtime_ns:
        _song_choices_cache = load_song_choices()
        _song_choices_mtime_ns = current_mtime_ns
    return _song_choices_cache

def resolve_song_selection(selection_text: str, song_choices: list[Path]) -> Path | None:
    selection = selection_text.strip()
    if not selection:
        return None

    if selection.isdigit():
        selected_index = int(selection) - 1
        if selected_index in range(len(song_choices)):
            return song_choices[selected_index]
        print(f"Invalid song number: {selection}")
        return None

    candidate_path = Path(selection)
    if candidate_path.exists() and candidate_path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return candidate_path

    normalized = selection.casefold()
    exact_matches = [
        path for path in song_choices
        if path.stem.casefold() == normalized or path.name.casefold() == normalized
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = [
        path for path in song_choices
        if normalized in path.stem.casefold() or normalized in path.name.casefold()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]

    if len(exact_matches) > 1 or len(partial_matches) > 1:
        matches = exact_matches or partial_matches
        print("Multiple songs matched. Be more specific:")
        for path in matches:
            print(f"  - {path.stem}")
        return None

    print(f"Song not found: {selection!r}")
    return None

def countdown_before_playback(seconds: int) -> None:
    for remaining in range(max(seconds, 0), 0, -1):
        print(f"\rPlaying song in {remaining}", end='', flush=True)
        time.sleep(1)
    if seconds > 0:
        print("\r" + " " * 32 + "\r", end='', flush=True)

def ensure_sky_ready() -> bool:
    inputs.sky = inputs.get_sky_window()
    if inputs.sky is None:
        print("Sky was not detected. Open Sky before playing a song.")
        return False
    inputs.focusWindow()
    if not inputs.is_sky_active():
        print("Sky is not focused yet. Bring Sky to the foreground, then press Enter to continue.")
        input()
    return True

# --- Vòng 6.1: Bộ chọn Nhạc Tương tác có theme rõ ràng, dễ mở rộng ---
import shutil
import unicodedata

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import TextArea
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

THEME_PRESETS = {
    "aurora": {
        "pointer": "❯",
        "song_icon": "♪",
        "empty_icon": "◇",
        "style": {
            "title": "fg:#a78bfa bold",
            "subtitle": "fg:#94a3b8",
            "divider": "fg:#334155",
            "input": "fg:#e2e8f0",
            "prompt": "fg:#38bdf8 bold",
            "results": "",
            "selected": "fg:#020617 bg:#38bdf8 bold",
            "unselected": "fg:#cbd5e1",
            "index": "fg:#64748b",
            "match": "fg:#fbbf24 bold",
            "muted": "fg:#64748b",
            "empty": "fg:#f97316 italic",
            "footer": "fg:#94a3b8",
            "key": "fg:#fbbf24 bold",
            "detail": "fg:#cbd5e1",
            "detail_label": "fg:#38bdf8 bold",
        },
    },
    "minimalist": {
        "pointer": "❯",
        "song_icon": "♪",
        "empty_icon": "·",
        "style": {
            "title": "fg:#e5e7eb bold",
            "subtitle": "fg:#9ca3af",
            "divider": "fg:#4b5563",
            "input": "fg:#e5e7eb",
            "prompt": "fg:#e5e7eb bold",
            "results": "",
            "selected": "fg:#00ffcc bold",
            "unselected": "fg:#cccccc",
            "index": "fg:#777777",
            "match": "fg:#ffffff bold",
            "muted": "fg:#777777",
            "empty": "fg:#999999 italic",
            "footer": "fg:#666666 italic",
            "key": "fg:#cccccc bold",
            "detail": "fg:#999999",
            "detail_label": "fg:#cccccc bold",
        },
    },
    "slate": {
        "pointer": "▌",
        "song_icon": "♫",
        "empty_icon": "□",
        "style": {
            "title": "fg:#cbd5e1 bold",
            "subtitle": "fg:#64748b",
            "divider": "fg:#475569",
            "input": "fg:#f8fafc",
            "prompt": "fg:#22d3ee bold",
            "results": "",
            "selected": "fg:#0f172a bg:#22d3ee bold",
            "unselected": "fg:#cbd5e1",
            "index": "fg:#64748b",
            "match": "fg:#67e8f9 bold",
            "muted": "fg:#64748b",
            "empty": "fg:#fca5a5 italic",
            "footer": "fg:#cbd5e1",
            "key": "fg:#67e8f9 bold",
            "detail": "fg:#cbd5e1",
            "detail_label": "fg:#67e8f9 bold",
        },
    },
    "cyberpunk": {
        "pointer": "➜",
        "song_icon": "✦",
        "empty_icon": "×",
        "style": {
            "title": "fg:#ffcc00 bold",
            "subtitle": "fg:#00ffcc",
            "divider": "fg:#7c3aed",
            "input": "fg:#00ffcc",
            "prompt": "fg:#ff00ff bold",
            "results": "",
            "selected": "fg:#0a0014 bg:#ffcc00 bold",
            "unselected": "fg:#b8b8ff",
            "index": "fg:#7c3aed",
            "match": "fg:#ff00ff bold",
            "muted": "fg:#777777",
            "empty": "fg:#ff00ff italic",
            "footer": "fg:#00ffcc",
            "key": "fg:#ffcc00 bold",
            "detail": "fg:#00ffcc",
            "detail_label": "fg:#ff00ff bold",
        },
    },
    "classic": {
        "pointer": ">",
        "song_icon": "-",
        "empty_icon": "!",
        "style": {
            "title": "fg:#ffffff bold",
            "subtitle": "fg:#ffffff",
            "divider": "fg:#ffffff",
            "input": "fg:#ffffff",
            "prompt": "fg:#ffffff bold",
            "results": "",
            "selected": "fg:#ffffff bold reverse",
            "unselected": "fg:#ffffff",
            "index": "fg:#ffffff",
            "match": "fg:#ffffff bold underline",
            "muted": "fg:#ffffff",
            "empty": "fg:#ffffff",
            "footer": "fg:#ffffff",
            "key": "fg:#ffffff bold",
            "detail": "fg:#ffffff",
            "detail_label": "fg:#ffffff bold",
        },
    },
}


def get_theme(theme_name: str | None = None) -> tuple[str, dict[str, Any]]:
    requested_theme = (theme_name or ACTIVE_THEME or "aurora").casefold()
    return requested_theme, THEME_PRESETS.get(requested_theme, THEME_PRESETS["aurora"])


def remove_accents(input_str: str) -> str:
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    res = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return res.replace('đ', 'd').replace('Đ', 'D')


def normalized_index_map(text: str) -> tuple[str, list[int]]:
    normalized_chars = []
    index_map = []
    for original_index, char in enumerate(text):
        normalized = remove_accents(char).casefold()
        for normalized_char in normalized:
            normalized_chars.append(normalized_char)
            index_map.append(original_index)
    return "".join(normalized_chars), index_map


def get_match_span(text: str, normalized_query: str) -> tuple[int, int] | None:
    if not normalized_query:
        return None
    normalized_text, index_map = normalized_index_map(text)
    match_start = normalized_text.find(normalized_query)
    if match_start == -1 or not index_map:
        return None
    match_end = match_start + len(normalized_query) - 1
    return index_map[match_start], index_map[match_end] + 1


def append_highlighted_song_name(lines: list[tuple[str, str]], song_name: str, normalized_query: str, selected: bool = False) -> None:
    if selected:
        lines.append(("class:selected", song_name))
        return

    span = get_match_span(song_name, normalized_query)
    if span is None:
        lines.append(("class:unselected", song_name))
        return

    start, end = span
    lines.append(("class:unselected", song_name[:start]))
    lines.append(("class:match", song_name[start:end]))
    lines.append(("class:unselected", song_name[end:]))


def truncate_text(text: str, max_width: int) -> str:
    if max_width <= 1:
        return "…"
    if len(text) <= max_width:
        return text
    return text[: max_width - 1] + "…"


def choose_song_interactively(theme_name: str | None = None) -> Path | None:
    if not HAS_PROMPT_TOOLKIT:
        return None

    song_choices = get_song_choices(force_refresh=True)
    if not song_choices:
        return None

    active_theme_name, theme = get_theme(theme_name)
    current_theme_name = active_theme_name
    style = Style.from_dict(theme["style"])
    pointer = theme["pointer"]
    song_icon = theme["song_icon"]
    empty_icon = theme["empty_icon"]

    song_indices = {path: idx for idx, path in enumerate(song_choices, start=1)}
    selected_index = 0
    filtered_songs = list(song_choices)
    result_window_height = 12

    search_field = TextArea(
        prompt=[("class:prompt", "Search song: ")],
        multiline=False,
        style="class:input",
    )
    header_control = FormattedTextControl(text="")
    results_control = FormattedTextControl(text="")
    detail_control = FormattedTextControl(text="")
    footer_control = FormattedTextControl(text="")

    header_window = Window(content=header_control, height=3)
    results_window = Window(content=results_control, height=result_window_height, style="class:results")
    detail_window = Window(content=detail_control, height=2, style="class:detail")
    footer_window = Window(content=footer_control, height=1, style="class:footer")

    layout = Layout(
        HSplit([
            header_window,
            search_field,
            results_window,
            detail_window,
            footer_window,
        ])
    )

    kb = KeyBindings()

    def build_header_text() -> list[tuple[str, str]]:
        terminal_width = max(48, shutil.get_terminal_size((80, 24)).columns)
        title = " SKY MUSIC PICKER "
        meta = f" {len(song_choices)} songs • theme: {current_theme_name} "
        divider = "─" * min(terminal_width, 96)
        return [
            ("class:title", title),
            ("class:subtitle", meta + "\n"),
            ("class:divider", divider + "\n"),
        ]

    def build_footer_text() -> list[tuple[str, str]]:
        return [
            ("class:key", "↑/↓"),
            ("class:footer", " move  "),
            ("class:key", "Enter"),
            ("class:footer", " play  "),
            ("class:key", "Ctrl+T"),
            ("class:footer", " theme  "),
            ("class:key", "Esc"),
            ("class:footer", " quit  "),
            ("class:key", "Ctrl+R"),
            ("class:footer", " refresh"),
        ]

    def filter_songs(query: str) -> list[Path]:
        if not query:
            return list(song_choices)

        is_digit_query = query.isdigit()
        target_idx = int(query) if is_digit_query else -1
        matches = []
        startswith_matches = []
        contains_matches = []

        for path in song_choices:
            orig_idx = song_indices[path]
            normalized_name = remove_accents(path.stem).casefold()
            if is_digit_query and orig_idx == target_idx:
                matches.append(path)
            elif normalized_name.startswith(query):
                startswith_matches.append(path)
            elif query in normalized_name:
                contains_matches.append(path)

        return matches + startswith_matches + contains_matches

    def build_result_text(query: str) -> list[tuple[str, str]]:
        terminal_width = max(48, shutil.get_terminal_size((80, 24)).columns)
        name_width = max(20, min(terminal_width - 16, 72))
        lines = []

        if not filtered_songs:
            lines.extend([
                ("class:empty", f"  {empty_icon} No songs found for "),
                ("class:match", search_field.text.strip() or "empty query"),
                ("class:empty", "\n"),
                ("class:muted", "    Try another keyword, number, or press Ctrl+R to reload songs.\n"),
            ])
            return lines

        start_idx = max(0, selected_index - result_window_height // 2)
        end_idx = min(len(filtered_songs), start_idx + result_window_height)
        if end_idx - start_idx < result_window_height:
            start_idx = max(0, end_idx - result_window_height)

        if start_idx > 0:
            lines.append(("class:muted", f"    … {start_idx} more above\n"))

        visible_end = end_idx - (1 if start_idx > 0 else 0)
        if end_idx < len(filtered_songs):
            visible_end = max(start_idx, visible_end - 1)

        for idx in range(start_idx, visible_end):
            path = filtered_songs[idx]
            orig_idx = song_indices[path]
            selected = idx == selected_index
            song_name = truncate_text(path.stem, name_width)

            if selected:
                lines.append(("class:selected", f" {pointer} {orig_idx:>3}) {song_icon} "))
                append_highlighted_song_name(lines, song_name, query, selected=True)
                lines.append(("class:selected", "\n"))
            else:
                lines.append(("class:unselected", "   "))
                lines.append(("class:index", f"{orig_idx:>3}) "))
                lines.append(("class:muted", f"{song_icon} "))
                append_highlighted_song_name(lines, song_name, query, selected=False)
                lines.append(("class:unselected", "\n"))

        if end_idx < len(filtered_songs):
            remaining = len(filtered_songs) - visible_end
            lines.append(("class:muted", f"    … {remaining} more below\n"))

        return lines

    def build_detail_text() -> list[tuple[str, str]]:
        query_text = search_field.text.strip()
        if not filtered_songs:
            return [
                ("class:detail_label", " Results "),
                ("class:detail", "0 matches"),
                ("class:detail", "\n"),
            ]

        selected_song = filtered_songs[selected_index]
        orig_idx = song_indices[selected_song]
        total_matches = len(filtered_songs)
        query_label = query_text if query_text else "all songs"
        path_label = truncate_text(str(selected_song), max(40, shutil.get_terminal_size((80, 24)).columns - 12))
        return [
            ("class:detail_label", " Selected "),
            ("class:detail", f"#{orig_idx} of {len(song_choices)} • {total_matches} match(es) • query: {query_label}\n"),
            ("class:detail_label", " File     "),
            ("class:detail", path_label),
        ]

    def update_ui() -> None:
        nonlocal selected_index, filtered_songs
        query = remove_accents(search_field.text).casefold().strip()
        previous_selected_song = filtered_songs[selected_index] if filtered_songs else None
        filtered_songs = filter_songs(query)

        if not filtered_songs:
            selected_index = 0
        elif previous_selected_song in filtered_songs:
            selected_index = filtered_songs.index(previous_selected_song)
        else:
            selected_index = min(max(0, selected_index), len(filtered_songs) - 1)

        header_control.text = build_header_text()
        results_control.text = build_result_text(query)
        detail_control.text = build_detail_text()
        footer_control.text = build_footer_text()

    search_field.buffer.on_text_changed += lambda _buf: update_ui()

    @kb.add("up")
    def move_up(event):
        nonlocal selected_index
        if filtered_songs:
            selected_index = (selected_index - 1) % len(filtered_songs)
            update_ui()

    @kb.add("down")
    def move_down(event):
        nonlocal selected_index
        if filtered_songs:
            selected_index = (selected_index + 1) % len(filtered_songs)
            update_ui()

    @kb.add("enter")
    def accept_selection(event):
        if filtered_songs:
            event.app.exit(result=filtered_songs[selected_index])
        else:
            event.app.exit(result=None)

    @kb.add("escape")
    @kb.add("c-c")
    def cancel(event):
        event.app.exit(result=None)



    @kb.add("c-r")
    def reload_songs(event):
        nonlocal song_choices, song_indices, selected_index, filtered_songs
        song_choices = get_song_choices(force_refresh=True)
        song_indices = {path: idx for idx, path in enumerate(song_choices, start=1)}
        selected_index = 0
        filtered_songs = list(song_choices)
        search_field.text = ""
        update_ui()

    @kb.add("c-t")
    def cycle_theme(event):
        nonlocal current_theme_name, pointer, song_icon, empty_icon
        themes_list = list(THEME_PRESETS.keys())
        current_idx = themes_list.index(current_theme_name)
        next_idx = (current_idx + 1) % len(themes_list)
        current_theme_name = themes_list[next_idx]

        _, new_theme = get_theme(current_theme_name)
        pointer = new_theme["pointer"]
        song_icon = new_theme["song_icon"]
        empty_icon = new_theme["empty_icon"]

        event.app.style = Style.from_dict(new_theme["style"])

        global ACTIVE_THEME
        ACTIVE_THEME = current_theme_name
        save_theme(current_theme_name)

        update_ui()

    update_ui()

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )

    return app.run()
