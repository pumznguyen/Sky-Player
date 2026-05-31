
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import shutil

from sky_music.ui.picker_theme import (
    THEME_PRESETS,
    get_theme,
    remove_accents,
    normalized_index_map,
    get_match_span,
    append_highlighted_song_name,
    truncate_text,
)
from sky_music.ui.picker_helpers import (
    SONG_DIR,
    SUPPORTED_EXTENSIONS,
    load_saved_theme,
    save_theme,
    load_song_choices,
    get_song_choices,
    resolve_song_selection,
    countdown_before_playback,
    ensure_sky_ready,
)
from sky_music.ui.picker_layout import (
    ActionHint,
    format_actions,
    _format_duration,
    build_box,
    build_header_box,
    format_song_row,
    format_info_str,
)
from sky_music.ui.picker_metadata import (
    SongUiMetadata,
    get_song_ui_metadata,
    get_cached_song_ui_metadata,
    clear_metadata_cache,
    _get_song_recommendation,
)
from sky_music.domain.session_context import PlaybackSessionContext

ACTIVE_THEME: str = load_saved_theme()

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import HSplit, Window, ConditionalContainer
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import TextArea
    from prompt_toolkit.filters import Condition
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

@dataclass
class PickerState:
    """Encapsulates the mutable state for the song picker UI."""
    song_choices: list[Path]
    selected_index: int = 0
    filtered_songs: list[Path] = None  # type: ignore
    
    current_view: Literal["picker", "preview", "profile_select", "tempo_select", "fps_select", "calibration", "help"] = "picker"
    previous_view: Literal["picker", "preview"] = "picker"
    
    current_profile: str = "balanced"
    current_tempo: float = 1.0
    current_fps: int | None = None
    dry_run_mode: bool = False
    
    risk_hint: str = ""
    temp_profile: str = "balanced"
    temp_tempo: float = 1.0
    temp_fps: int | None = None

    def __post_init__(self):
        if self.filtered_songs is None:
            self.filtered_songs = list(self.song_choices)

@dataclass(frozen=True, slots=True)
class SongPickerResult:
    """Carries the user's confirmed decision from the song picker."""
    song_path: Path
    action: Literal["play", "dry_run"]
    profile_name: str
    tempo_scale: float
    fps: int | None = None
    verbose_hud: bool | None = None
    telemetry_enabled: bool | None = None

PROFILES_INFO = [
    ("local-precise", "Best local timing, less safe for remote listeners"),
    ("balanced", "Default balanced setting"),
    ("remote-safe", "Better clarity for other players"),
    ("dense-safe", "Safer for fast repeats and dense songs"),
]

TEMPO_OPTIONS = [
    (0.90, "safer for listeners"),
    (0.95, "recommended for medium/high risk songs"),
    (1.00, "original speed"),
    (1.05, "faster"),
    (1.10, "high risk"),
]

FPS_OPTIONS = [
    (None, "Auto (No forced sync)"),
    (30, "30 FPS (Mobile/Emulator)"),
    (60, "60 FPS (Standard)"),
    (120, "120 FPS (High Refresh)"),
    (144, "144 FPS (High Refresh)"),
]

def safe_exit(app: Any, result: SongPickerResult | None) -> None:
    future = getattr(app, "future", None)
    if future is not None and future.done():
        return
    try:
        app.exit(result=result)
    except Exception:
        pass

def choose_song_interactively(
    theme_name: str | None = None,
    initial_profile: str = "balanced",
    initial_tempo: float = 1.0,
    initial_fps: int | None = None,
    initial_dry_run: bool = False,
    scan_code_mode: str = "physical",
) -> SongPickerResult | None:
    if not HAS_PROMPT_TOOLKIT:
        return None

    song_choices = get_song_choices(force_refresh=True)
    if not song_choices:
        return None

    from sky_music.config import (
        load_config,
        save_config,
        canonical_profile_name,
        persist_calibration_defaults,
        persist_default_fps,
        persist_default_profile,
        persist_default_tempo,
    )
    from sky_music.orchestration.calibration import (
        calibrate_profile,
        calibration_input_from_summary,
        load_latest_telemetry_summary,
    )

    state = PickerState(song_choices=song_choices)
    state.current_profile = canonical_profile_name(initial_profile)
    state.current_tempo = initial_tempo
    state.current_fps = initial_fps
    state.dry_run_mode = initial_dry_run
    state.temp_profile = state.current_profile
    state.temp_tempo = state.current_tempo
    state.temp_fps = state.current_fps

    user_cfg = load_config()
    verbose_hud_mode = user_cfg.verbose_hud
    telemetry_mode = user_cfg.telemetry_enabled_by_default

    def picker_session() -> PlaybackSessionContext:
        return PlaybackSessionContext(
            profile_name=state.current_profile,
            tempo_scale=state.current_tempo,
            fps=state.current_fps,
            scan_code_mode=scan_code_mode,
        )

    def build_picker_result() -> SongPickerResult:
        return SongPickerResult(
            state.filtered_songs[state.selected_index],
            "dry_run" if state.dry_run_mode else "play",
            state.current_profile,
            state.current_tempo,
            state.current_fps,
            verbose_hud=verbose_hud_mode,
            telemetry_enabled=telemetry_mode,
        )

    active_theme_name, theme = get_theme(theme_name or ACTIVE_THEME)
    current_theme_name = active_theme_name
    style_dict = theme["style"]
    style = Style.from_dict(style_dict)
    pointer = theme["pointer"]
    song_icon = theme["song_icon"]
    empty_icon = theme["empty_icon"]
    theme_names = list(THEME_PRESETS.keys())

    song_indices = {path: idx for idx, path in enumerate(song_choices, start=1)}

    search_field = TextArea(
        prompt=[("class:prompt", "Search: ")],
        multiline=False,
        style="class:input",
    )
    
    is_picker_view = Condition(lambda: state.current_view == "picker")
    search_container = ConditionalContainer(search_field, filter=is_picker_view)

    header_control = FormattedTextControl(text="")
    results_control = FormattedTextControl(text="")
    detail_control = FormattedTextControl(text="")
    footer_control = FormattedTextControl(text="")

    def get_layout_heights() -> tuple[int, int]:
        term_height = shutil.get_terminal_size((80, 24)).lines
        if state.current_view == "picker":
            overhead = 9
            available = max(0, term_height - overhead)
            if available >= 18:
                return 13, 5
            elif available >= 10:
                return available - 5, 4
            else:
                return max(3, available), 0
        elif state.current_view == "preview":
            overhead = 8
            available = max(0, term_height - overhead)
            has_warnings = False
            if state.filtered_songs:
                metadata = get_cached_song_ui_metadata(state.filtered_songs[state.selected_index], picker_session())
                if metadata.risk != "low":
                    has_warnings = True
            if not has_warnings:
                return min(11, available), 0
            if available >= 16:
                return 11, 5
            elif available >= 13:
                return 10, 3
            else:
                return max(3, available), 0
        elif state.current_view in {"profile_select", "tempo_select", "fps_select", "calibration", "help"}:
            overhead = 8
            available = max(0, term_height - overhead)
            if state.current_view == "profile_select": return min(len(PROFILES_INFO) + 2, available), 0
            if state.current_view == "tempo_select": return min(len(TEMPO_OPTIONS) + 3, available), 0
            if state.current_view == "fps_select": return min(len(FPS_OPTIONS) + 3, available), 0
            if state.current_view == "calibration": return min(10, available), 0
            if state.current_view == "help": return min(17, available), 0
        return 13, 5

    def get_results_height() -> int: return get_layout_heights()[0]
    def get_detail_height() -> int: return get_layout_heights()[1]

    header_window = Window(content=header_control, height=3)
    results_window = Window(content=results_control, height=get_results_height, style="class:results")
    detail_window = Window(content=detail_control, height=get_detail_height, style="class:detail")
    footer_window = Window(content=footer_control, height=7, style="class:footer")

    layout = Layout(
        HSplit([
            header_window,
            search_container,
            results_window,
            detail_window,
            footer_window,
        ])
    )

    kb = KeyBindings()

    def build_header_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))

        mode_label = {
            "picker": "Picker", "preview": "Preview", "profile_select": "Profile Selection",
            "tempo_select": "Tempo Adjustment", "fps_select": "FPS Selection",
            "calibration": "Calibration", "help": "Help Guide"
        }.get(state.current_view, "Picker")

        dry_str = "ON" if state.dry_run_mode else "OFF"
        hud_str = "ON" if verbose_hud_mode else "OFF"
        fps_str = str(state.current_fps) if state.current_fps else "Auto"
        telem_str = "ON" if telemetry_mode else "OFF"

        parts = [
            mode_label, f"profile: {state.current_profile}", f"tempo: {state.current_tempo:.2f}x",
            f"fps: {fps_str}", f"dry: {dry_str}", f"hud: {hud_str}", f"telem: {telem_str}",
            f"theme: {current_theme_name}", f"songs: {len(state.song_choices)}",
        ]
        return build_header_box("SKY MUSIC PLAYER", parts, terminal_width)

    def build_results_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        if state.current_view == "picker":
            header_str = f"  #   {'Song Title':<36}    Time   Notes   Risk    Suggested\n"
            divider_str = f"  ──  {'─' * 36}    ────   ─────   ─────   ───────────\n"
            lines = [("class:divider", header_str), ("class:divider", divider_str)]
            
            if not state.filtered_songs:
                lines.append(("class:empty", f"  {empty_icon} No songs found\n"))
                return lines
                
            r_height, _ = get_layout_heights()
            max_visible = max(1, r_height - 2)
            start_idx = max(0, state.selected_index - max_visible // 2)
            end_idx = min(len(state.filtered_songs), start_idx + max_visible)
            if end_idx - start_idx < max_visible: start_idx = max(0, end_idx - max_visible)
                
            for idx in range(start_idx, end_idx):
                path = state.filtered_songs[idx]
                orig_idx = song_indices[path]
                metadata = get_cached_song_ui_metadata(path, picker_session())
                lines.extend(format_song_row(orig_idx, metadata, idx == state.selected_index, search_field.text.strip(), pointer, song_icon))
            return lines
            
        elif state.current_view == "preview":
            if not state.filtered_songs: return []
            metadata = get_cached_song_ui_metadata(state.filtered_songs[state.selected_index], picker_session())
            
            preview_content = [
                f"{metadata.name}",
                f"Time {_format_duration(metadata.duration_seconds)} │ Notes {metadata.note_count} │ Polyphony {metadata.max_polyphony}",
                f"Risk {metadata.risk.upper()} │ Stress: {metadata.timing_stress_rate:.1f}% ({metadata.impossible_repeats} conflicts)",
                f"Min repeat gap: {metadata.min_same_key_gap_ms:.0f}ms │ Peak density: {metadata.peak_notes_per_second_1s:.1f} n/s",
            ]
            
            effective = picker_session().resolve_effective_policy(user_cfg)
            lead_ms = effective.input_lead_us // 1000
            
            timing_content = [
                f"Current:   {state.current_profile} @ {state.current_tempo:.2f}x (lead: {lead_ms}ms)",
                f"Suggested: {metadata.recommended_profile} @ {metadata.recommended_tempo_scale:.2f}x",
                f"FPS Sync:  {state.current_fps or 'Auto'}"
            ]
            return build_box("Song Detail", preview_content, width=terminal_width) + build_box("Timing Settings", timing_content, width=terminal_width)
            
        elif state.current_view == "profile_select":
            content = []
            for name, desc in PROFILES_INFO:
                bullet = "●" if name == state.current_profile else "○"
                row = f"{bullet} {name:<15}   {desc}"
                content.append([("class:selected" if name == state.temp_profile else "class:unselected", f" {'➜' if name == state.temp_profile else ' '} {row}")])
            return build_box("Select Timing Profile", content, width=terminal_width)
            
        elif state.current_view == "tempo_select":
            content = [f"Adjust: {state.temp_tempo:.2f}x", ""]
            for val, desc in TEMPO_OPTIONS:
                bullet = "●" if abs(val - state.current_tempo) < 0.005 else "○"
                row = f"{bullet} {val:.2f}x   {desc}"
                content.append([("class:selected" if abs(val - state.temp_tempo) < 0.005 else "class:unselected", f" {'➜' if abs(val - state.temp_tempo) < 0.005 else ' '} {row}")])
            return build_box("Adjust Tempo", content, width=terminal_width)

        elif state.current_view == "fps_select":
            content = [f"Target: {state.temp_fps if state.temp_fps else 'Auto'}", ""]
            for val, desc in FPS_OPTIONS:
                bullet = "●" if val == state.current_fps else "○"
                val_str = str(val) if val else "Auto"
                row = f"{bullet} {val_str:<4}   {desc}"
                content.append([("class:selected" if val == state.temp_fps else "class:unselected", f" {'➜' if val == state.temp_fps else ' '} {row}")])
            return build_box("FPS Sync Selection", content, width=terminal_width)

        elif state.current_view == "calibration":
            summary = load_latest_telemetry_summary()
            if summary is None:
                return build_box(
                    "Telemetry Calibration",
                    ["No telemetry summary found in logs/.", "Run playback with --debug-csv first."],
                    width=terminal_width,
                )
            inp = calibration_input_from_summary(summary)
            rec = calibrate_profile(inp)
            content = [
                f"Latest: {summary.get('song', 'Unknown')} @ {inp.fps} FPS",
                f"Profile: {inp.profile_name} -> {rec.profile_name}",
                f"Tempo:   {inp.tempo_scale:.2f}x -> {rec.tempo_scale:.2f}x",
                f"Lead:    {rec.input_lead_us / 1000:.1f}ms",
                f"Hold:    {rec.hold_us / 1000:.1f}ms",
                f"Severity {rec.severity.upper()}",
                rec.reason,
            ]
            return build_box("Telemetry Calibration", content, width=terminal_width)

        elif state.current_view == "help":
            help_lines = [
                ("Enter", "Play selected song"), ("Space", "Quick Play"), ("V", "View song details"),
                ("P", "Timing Profile"), ("T", "Adjust Tempo"), ("F", "FPS Selection"), ("C", "Calibration"),
                ("D", "Toggle Dry-Run"), ("F2/F3", "HUD/Telemetry"), ("Ctrl+T/R", "Theme/Reload"),
                ("H/Esc", "Help / Back")
            ]
            content = [[("class:key", f"  {k:<10}"), ("class:detail", d)] for k, d in help_lines]
            return build_box("Keyboard Shortcuts", content, width=terminal_width)
        return []

    def build_detail_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        _, d_height = get_layout_heights()
        if d_height == 0 or not state.filtered_songs: return []
        metadata = get_cached_song_ui_metadata(state.filtered_songs[state.selected_index], picker_session())
        content = [metadata.name]
        if d_height >= 6:
            content.append(
                f"Time {_format_duration(metadata.duration_seconds)} │ "
                f"Notes {metadata.note_count} │ Risk {metadata.risk.upper()}"
            )
            content.append(f"Poly: {metadata.max_polyphony} │ Gap: {metadata.min_same_key_gap_ms:.0f}ms")
            content.append(
                f"Density: {metadata.average_notes_per_second:.1f}/s "
                f"(peak {metadata.peak_notes_per_second_1s:.1f}/s)"
            )
        elif d_height >= 4:
            content.append(
                f"Time {_format_duration(metadata.duration_seconds)} │ Notes {metadata.note_count} │ "
                f"Risk {metadata.risk.upper()}"
            )
            content.append(f"Poly: {metadata.max_polyphony} │ Density: {metadata.average_notes_per_second:.1f}/s")
        else:
            content.append(
                f"Time {_format_duration(metadata.duration_seconds)} │ Notes {metadata.note_count} │ "
                f"Risk {metadata.risk.upper()}"
            )
        return build_box("Selected", content, width=terminal_width)

    def build_footer_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        if state.current_view in {"picker", "preview"}:
            if not state.filtered_songs: return []
            meta = get_cached_song_ui_metadata(state.filtered_songs[state.selected_index], picker_session())
            risk_style = "fg:#f97316 bold" if meta.risk == "high" else ("fg:#fbbf24 bold" if meta.risk == "medium" else "fg:#10b981")
            line1 = [(risk_style, f"{meta.risk.upper()} risk: "), ("class:detail", f"Suggested {meta.recommended_profile} @ {meta.recommended_tempo_scale:.2f}x")]
            
            actions = [
                ActionHint("Enter", "play", "play", "play"),
                ActionHint("Space", "quick play", "quick", "sp"),
                ActionHint("V", "preview", "view", "v"),
                ActionHint("P", "profile", "prof", "p"),
                ActionHint("T", "tempo", "tempo", "t"),
                ActionHint("F", "fps", "fps", "f"),
                ActionHint("C", "calib", "cal", "c"),
                ActionHint("D", "dry-run", "dry", "d"),
                ActionHint("F2", "HUD", "hud", "h2"),
                ActionHint("F3", "telemetry", "telem", "h3"),
                ActionHint("^R", "reload songs", "reload", "rl"),
                ActionHint("^T", "theme", "theme", "th"),
                ActionHint("H", "help", "help", "h"),
                ActionHint("Esc", "quit", "quit", "q"),
            ]
            row_w = terminal_width - 4
            action_rows = [
                format_actions(actions[0:4], row_w),
                format_actions(actions[4:8], row_w),
                format_actions(actions[8:], row_w),
            ]
            return build_box("Actions", [line1, *action_rows], width=terminal_width)
        return build_box("Navigation", [[("class:footer", "Arrow keys to choose, Enter to apply, Esc to cancel")]], width=terminal_width)

    def update_ui():
        query = remove_accents(search_field.text).casefold().strip()
        state.filtered_songs = [p for p in state.song_choices if query in remove_accents(p.stem).casefold()]
        state.selected_index = max(0, min(state.selected_index, len(state.filtered_songs) - 1))
        header_control.text = build_header_text()
        results_control.text = build_results_text()
        detail_control.text = build_detail_text()
        footer_control.text = build_footer_text()

    search_field.buffer.on_text_changed += lambda _: update_ui()

    @kb.add("up")
    def _(event):
        if state.current_view == "picker": state.selected_index = (state.selected_index - 1) % len(state.filtered_songs)
        elif state.current_view == "profile_select":
            profiles = [p[0] for p in PROFILES_INFO]
            state.temp_profile = profiles[(profiles.index(state.temp_profile) - 1) % len(profiles)]
        elif state.current_view == "tempo_select":
            presets = [t[0] for t in TEMPO_OPTIONS]
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - state.temp_tempo))
            state.temp_tempo = presets[(idx - 1) % len(presets)]
        elif state.current_view == "fps_select":
            fps = [f[0] for f in FPS_OPTIONS]
            state.temp_fps = fps[(fps.index(state.temp_fps) - 1) % len(fps)]
        update_ui()

    @kb.add("down")
    def _(event):
        if state.current_view == "picker": state.selected_index = (state.selected_index + 1) % len(state.filtered_songs)
        elif state.current_view == "profile_select":
            profiles = [p[0] for p in PROFILES_INFO]
            state.temp_profile = profiles[(profiles.index(state.temp_profile) + 1) % len(profiles)]
        elif state.current_view == "tempo_select":
            presets = [t[0] for t in TEMPO_OPTIONS]
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - state.temp_tempo))
            state.temp_tempo = presets[(idx + 1) % len(presets)]
        elif state.current_view == "fps_select":
            fps = [f[0] for f in FPS_OPTIONS]
            state.temp_fps = fps[(fps.index(state.temp_fps) + 1) % len(fps)]
        update_ui()

    @kb.add("p")
    def _(event):
        state.previous_view, state.current_view, state.temp_profile = state.current_view, "profile_select", state.current_profile
        update_ui()

    @kb.add("t")
    def _(event):
        state.previous_view, state.current_view, state.temp_tempo = state.current_view, "tempo_select", state.current_tempo
        update_ui()

    @kb.add("f")
    def _(event):
        state.previous_view, state.current_view, state.temp_fps = state.current_view, "fps_select", state.current_fps
        update_ui()

    @kb.add("c")
    def _(event):
        if state.current_view in {"picker", "preview"}:
            state.previous_view, state.current_view = state.current_view, "calibration"
            update_ui()

    @kb.add("v")
    def _(event):
        if state.current_view == "picker": state.current_view = "preview"
        update_ui()

    @kb.add("d")
    def _(event): state.dry_run_mode = not state.dry_run_mode; update_ui()

    @kb.add("space")
    def _(event):
        if state.current_view in {"picker", "preview"} and state.filtered_songs:
            safe_exit(event.app, build_picker_result())

    @kb.add("c-r")
    def _(event):
        if state.current_view == "picker":
            clear_metadata_cache()
            state.song_choices = get_song_choices(force_refresh=True)
            state.filtered_songs = list(state.song_choices)
            state.selected_index = 0
            update_ui()

    @kb.add("f2")
    def _(event):
        nonlocal verbose_hud_mode
        if state.current_view == "picker":
            verbose_hud_mode = not verbose_hud_mode
            user_cfg.verbose_hud = verbose_hud_mode
            save_config(user_cfg)
            update_ui()

    @kb.add("f3")
    def _(event):
        nonlocal telemetry_mode
        if state.current_view == "picker":
            telemetry_mode = not telemetry_mode
            user_cfg.telemetry_enabled_by_default = telemetry_mode
            save_config(user_cfg)
            update_ui()

    @kb.add("c-t")
    def _(event):
        global ACTIVE_THEME
        nonlocal active_theme_name, current_theme_name, style_dict, style, pointer, song_icon, empty_icon
        if not theme_names:
            return
        try:
            current_index = theme_names.index(current_theme_name)
        except ValueError:
            current_index = -1
        next_theme = theme_names[(current_index + 1) % len(theme_names)]
        ACTIVE_THEME = next_theme
        save_theme(next_theme)
        active_theme_name, next_theme_data = get_theme(next_theme)
        current_theme_name = active_theme_name
        style_dict = next_theme_data["style"]
        style = Style.from_dict(style_dict)
        pointer = next_theme_data["pointer"]
        song_icon = next_theme_data["song_icon"]
        empty_icon = next_theme_data["empty_icon"]
        try:
            event.app.style = style
        except Exception:
            pass
        update_ui()

    @kb.add("c-c")
    def _(event):
        safe_exit(event.app, None)

    @kb.add("h")
    def _(event):
        state.previous_view, state.current_view = state.current_view, "help" if state.current_view != "help" else state.previous_view
        update_ui()

    @kb.add("enter")
    def _(event):
        if state.current_view in {"picker", "preview"}:
            if state.filtered_songs:
                safe_exit(event.app, build_picker_result())
        elif state.current_view == "profile_select":
            state.current_profile, state.current_view = state.temp_profile, "picker"
            try:
                persist_default_profile(load_config(), state.current_profile)
            except Exception:
                pass
        elif state.current_view == "tempo_select":
            state.current_tempo, state.current_view = state.temp_tempo, "picker"
            try:
                persist_default_tempo(load_config(), state.current_tempo)
            except Exception:
                pass
        elif state.current_view == "fps_select":
            state.current_fps, state.current_view = state.temp_fps, "picker"
            try:
                persist_default_fps(load_config(), state.current_fps)
            except Exception:
                pass
        elif state.current_view == "calibration":
            summary = load_latest_telemetry_summary()
            if summary is not None:
                try:
                    inp = calibration_input_from_summary(summary)
                    rec = calibrate_profile(inp)
                    persist_calibration_defaults(
                        load_config(),
                        profile_name=rec.profile_name,
                        tempo_scale=rec.tempo_scale,
                        fps=inp.fps,
                        input_lead_us=rec.input_lead_us,
                    )
                    state.current_profile = canonical_profile_name(rec.profile_name)
                    state.current_tempo = rec.tempo_scale
                    state.current_fps = inp.fps if inp.fps > 0 else None
                except Exception:
                    pass
            state.current_view = "picker"
        update_ui()

    @kb.add("escape")
    def _(event):
        if state.current_view == "picker": safe_exit(event.app, None)
        else: state.current_view = "picker"; update_ui()

    for path in song_choices:
        get_cached_song_ui_metadata(path, picker_session())

    update_ui()
    return Application(layout=layout, key_bindings=kb, style=style, full_screen=False).run()
