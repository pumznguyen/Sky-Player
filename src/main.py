import argparse
import sys
import time
from pathlib import Path

# Import từ các mô-đun chuyên biệt
import inputs
from inputs import (
    enable_high_precision_timers,
    disable_high_precision_timers,
    focusWindow
)
from ui import (
    PLAYBACK_FINISHED,
    PLAYBACK_SKIPPED,
    PLAYBACK_QUIT,
    PLAYBACK_POLL_SECONDS,
    PlaybackControls,
    ProgressRenderer,
    clear_terminal,
    parse_hotkey,
    hotkey_conflicts_with_note_keys
)
from songs import (
    SONG_DIR,
    SUPPORTED_EXTENSIONS,
    get_song_choices,
    resolve_song_selection,
    countdown_before_playback,
    ensure_sky_ready
)

PLAYBACK_DEBUG = False
CURRENT_SCAN_CODE_MODE = "physical"
DEBUG_LOG_PATH = None
DEBUG_START_PERF = None
DEBUG_LOG_BUFFER = []
TIMING_POLICY = None
TELEMETRY_CSV_ENABLED = False
DRY_RUN_MODE = False

def init_debug_log() -> None:
    global DEBUG_LOG_PATH, DEBUG_START_PERF
    DEBUG_START_PERF = time.perf_counter()
    debug_log_dir = Path("logs")
    debug_log_dir.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_PATH = debug_log_dir / f"playback_debug_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with DEBUG_LOG_PATH.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debug playback log started\n")

def debug_log(message: str) -> None:
    if not PLAYBACK_DEBUG:
        return
    now = time.perf_counter()
    rel = 0.0 if DEBUG_START_PERF is None else now - DEBUG_START_PERF
    DEBUG_LOG_BUFFER.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')} +{rel:.6f}s] {message}")

def flush_debug_log() -> None:
    global DEBUG_LOG_BUFFER
    if not PLAYBACK_DEBUG or DEBUG_LOG_PATH is None or not DEBUG_LOG_BUFFER:
        return
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write("\n".join(DEBUG_LOG_BUFFER) + "\n")
    except Exception as e:
        print(f"Failed to write logs: {e}")
    finally:
        DEBUG_LOG_BUFFER.clear()

# Kết nối hàm debug_log của main.py sang inputs.py để đồng bộ logging
inputs._debug_log_callback = debug_log

def play_selected_song(selected_song: Path, countdown_seconds: int, controls: PlaybackControls | None = None, force_dry_run: bool = False) -> str:
    from sky_music.parser import parse_song_file
    from sky_music.scheduler import build_key_actions
    from sky_music.backend import WinSendInputBackend, DryRunBackend
    from sky_music.playback import PlaybackEngine
    from ui import ProgressRenderer

    try:
        song = parse_song_file(selected_song)
    except Exception as exc:
        print(f"Failed to parse song: {exc}")
        return PLAYBACK_QUIT

    is_dry_run = DRY_RUN_MODE or force_dry_run

    # Check window/readiness only if we are NOT running dry-run mode
    if not is_dry_run:
        if not ensure_sky_ready():
            return PLAYBACK_QUIT
        if controls is not None and controls.enabled:
            print(f"Controls: {controls.hint()}")
        countdown_before_playback(countdown_seconds)
    else:
        print(f"[simulation] DRY-RUN enabled. Simulating playback of {song.name}...")

    # Build scheduled actions using specified TimingPolicy and selected mode
    sched_meta = build_key_actions(song, policy=TIMING_POLICY, scan_code_mode=CURRENT_SCAN_CODE_MODE)
    actions = sched_meta["actions"]

    backend = DryRunBackend() if is_dry_run else WinSendInputBackend()
    renderer = ProgressRenderer(controls)
    
    engine = PlaybackEngine(
        song=song,
        actions=actions,
        backend=backend,
        controls=controls,
        renderer=renderer,
        telemetry_enabled=TELEMETRY_CSV_ENABLED or PLAYBACK_DEBUG or force_dry_run,
        require_focus=not is_dry_run
    )
    return engine.play()



def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Play Sky song files from the terminal.",
    )
    parser.add_argument(
        "--song",
        help="play a song by number, exact name, partial name, or file path",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list available songs and exit",
    )
    parser.add_argument(
        "--songs-dir",
        type=Path,
        default=SONG_DIR,
        help="folder containing .json/.skysheet files",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=3,
        help="seconds to wait before playback starts",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="number of times to repeat the selected song",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="do not clear the terminal after each song",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="run complete clinical diagnostic system check",
    )
    parser.add_argument(
        "--doctor-timing",
        action="store_true",
        help="diagnose high-precision multimedia timers on Windows",
    )
    parser.add_argument(
        "--doctor-input",
        action="store_true",
        help="diagnose layout configurations and active depressed note keys conflicts",
    )
    parser.add_argument(
        "--debug-playback",
        action="store_true",
        help="write playback timing details to logs/",
    )
    parser.add_argument(
        "--pause-key",
        default="f8",
        help="global hotkey to pause/resume playback, e.g. f8 or ctrl+p",
    )
    parser.add_argument(
        "--skip-key",
        default="f9",
        help="global hotkey to skip the current song and return to song selection",
    )
    parser.add_argument(
        "--quit-key",
        default="esc",
        help="global hotkey to stop playback and exit",
    )
    parser.add_argument(
        "--refocus-key",
        default="f6",
        help="global hotkey to bring Sky back to the foreground",
    )
    parser.add_argument(
        "--disable-hotkeys",
        action="store_true",
        help="disable runtime hotkeys and only use Ctrl+C to stop",
    )
    parser.add_argument(
        "--allow-note-hotkeys",
        action="store_true",
        help="allow single-key hotkeys that overlap with note keys such as p; not recommended",
    )
    parser.add_argument(
        "--scan-code-mode",
        choices=["physical", "mapped"],
        default="physical",
        help="physical = fixed QWERTY scan codes, mapped = OS keyboard layout",
    )
    parser.add_argument(
        "--sky-process-names",
        default="Sky.exe,Sky Children of the Light.exe",
        help="comma-separated expected Sky executable names",
    )
    parser.add_argument(
        "--allow-title-fallback",
        action="store_true",
        help="allow title matching when process verification fails",
    )
    parser.add_argument(
        "--theme",
        choices=["aurora", "minimalist", "slate", "cyberpunk", "classic"],
        default=None,
        help="TUI selection menu theme: aurora, minimalist, slate, cyberpunk, or classic (Default: saved or aurora)",
    )
    parser.add_argument(
        "--timing-profile",
        choices=["fast", "balanced", "conservative"],
        default="balanced",
        help="Select timing profile (Default: balanced)",
    )
    parser.add_argument(
        "--hold-ms",
        type=int,
        help="Override key hold duration (in milliseconds)",
    )
    parser.add_argument(
        "--min-hold-ms",
        type=int,
        help="Override absolute minimum key hold duration (in milliseconds)",
    )
    parser.add_argument(
        "--release-gap-ms",
        type=int,
        help="Override release gap (in milliseconds)",
    )
    parser.add_argument(
        "--repeat-release-gap-ms",
        type=int,
        help="Override gap before same-key repeats (in milliseconds)",
    )
    parser.add_argument(
        "--debug-csv",
        action="store_true",
        help="Write high-precision timing CSV telemetry reports to logs/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run playback purely inside mock memory, without sending physical OS keystrokes (useful for timing diagnosis)",
    )
    return parser

def configure_from_args(args: argparse.Namespace) -> None:
    global PLAYBACK_DEBUG, DEBUG_LOG_PATH, CURRENT_SCAN_CODE_MODE, TIMING_POLICY, TELEMETRY_CSV_ENABLED, DRY_RUN_MODE
    import inputs
    import songs
    from sky_music.scheduler import TimingPolicy

    CURRENT_SCAN_CODE_MODE = args.scan_code_mode
    songs.SONG_DIR = args.songs_dir
    PLAYBACK_DEBUG = args.debug_playback
    inputs.PLAYBACK_DEBUG = args.debug_playback
    TELEMETRY_CSV_ENABLED = args.debug_csv
    DRY_RUN_MODE = args.dry_run

    if PLAYBACK_DEBUG:
        init_debug_log()

    # Determine base TimingPolicy from profile
    profile = args.timing_profile
    if profile == "fast":
        policy = TimingPolicy(
            hold_us=16_000,
            min_hold_us=8_000,
            release_gap_us=2_000,
            repeat_release_gap_us=2_000
        )
    elif profile == "conservative":
        policy = TimingPolicy(
            hold_us=34_000,
            min_hold_us=16_000,
            release_gap_us=5_000,
            repeat_release_gap_us=3_000
        )
    else: # balanced
        policy = TimingPolicy(
            hold_us=24_000,
            min_hold_us=12_000,
            release_gap_us=3_000,
            repeat_release_gap_us=2_000
        )

    # Perform overrides from arguments
    hold_us = args.hold_ms * 1000 if args.hold_ms is not None else policy.hold_us
    min_hold_us = args.min_hold_ms * 1000 if args.min_hold_ms is not None else policy.min_hold_us
    release_gap_us = args.release_gap_ms * 1000 if args.release_gap_ms is not None else policy.release_gap_us
    repeat_release_gap_us = args.repeat_release_gap_ms * 1000 if args.repeat_release_gap_ms is not None else policy.repeat_release_gap_us
    
    TIMING_POLICY = TimingPolicy(
        hold_us=hold_us,
        min_hold_us=min_hold_us,
        release_gap_us=release_gap_us,
        repeat_release_gap_us=repeat_release_gap_us
    )

    if args.sky_process_names:
        inputs.EXPECTED_PROCESS_NAMES = {
            name.strip()
            for name in args.sky_process_names.split(",")
            if name.strip()
        }

    inputs.ALLOW_TITLE_FALLBACK = bool(args.allow_title_fallback)
    if args.theme is not None:
        songs.ACTIVE_THEME = args.theme
        songs.save_theme(args.theme)

def build_playback_controls(args: argparse.Namespace) -> PlaybackControls:
    if args.disable_hotkeys:
        return PlaybackControls(
            pause=parse_hotkey(args.pause_key),
            skip=parse_hotkey(args.skip_key),
            quit=parse_hotkey(args.quit_key),
            refocus=parse_hotkey(args.refocus_key),
            enabled=False,
        )

    controls = PlaybackControls(
        pause=parse_hotkey(args.pause_key),
        skip=parse_hotkey(args.skip_key),
        quit=parse_hotkey(args.quit_key),
        refocus=parse_hotkey(args.refocus_key),
    )

    conflicting = [
        ("pause", controls.pause),
        ("skip", controls.skip),
        ("quit", controls.quit),
        ("refocus", controls.refocus),
    ]
    unsafe = [f"{name}={hotkey.display}" for name, hotkey in conflicting if hotkey_conflicts_with_note_keys(hotkey)]
    if unsafe and not args.allow_note_hotkeys:
        raise ValueError(
            "Hotkey overlaps with note keys: "
            + ", ".join(unsafe)
            + ". Use Ctrl/Alt/Shift, a function key, or pass --allow-note-hotkeys if you accept the risk."
        )
    return controls

def prompt_song_selection() -> Path | None:
    import songs
    if songs.HAS_PROMPT_TOOLKIT:
        return songs.choose_song_interactively()

    # Chế độ dự phòng (Fallback) nếu môi trường không có prompt_toolkit
    song_choices = get_song_choices(force_refresh=True)
    songs.print_song_choices = lambda choices: print_choices_local(choices)
    print_choices_local(song_choices)

    while True:
        print("Commands: number/name = play, r = refresh, q = quit")
        selection = input("Select song: ").strip()

        if selection.casefold() in {"q", "quit", "exit", "0"}:
            return None
        if selection.casefold() in {"r", "refresh"}:
            clear_terminal()
            song_choices = get_song_choices(force_refresh=True)
            print_choices_local(song_choices)
            continue

        selected_song = resolve_song_selection(selection, song_choices)
        if selected_song is not None:
            return selected_song
        print("")

def print_choices_local(song_choices: list[Path]) -> None:
    if not song_choices:
        print(f"No songs found in: {SONG_DIR.resolve()}")
        print(f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return
    print("Songs:")
    for index, path in enumerate(song_choices, start=1):
        print(f"  {index:>2}) {path.stem}")

def main() -> int:
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = build_arg_parser()
    args = parser.parse_args()
    configure_from_args(args)
    try:
        controls = build_playback_controls(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.doctor or args.doctor_timing or args.doctor_input:
        import sky_music.doctor as doctor
        if args.doctor:
            doctor.run_all_doctor_checks()
        elif args.doctor_timing:
            print("=" * 60)
            print("             SKY TIMING DOCTOR")
            print("=" * 60)
            diag = doctor.check_timer_resolution()
            print(f"Status: {'OK' if diag['ok'] else 'FAILED'}\nDetails: {diag['msg']}")
            print("=" * 60)
        elif args.doctor_input:
            print("=" * 60)
            print("             SKY INPUT DOCTOR")
            print("=" * 60)
            kb_diag = doctor.check_keyboard_layout()
            conflict_diag = doctor.check_physical_keys_held()
            print(f"Layout Mapping : {'OK' if kb_diag['ok'] else 'FAILED'} - {kb_diag['msg']}")
            print(f"Key Conflicts  : {'OK' if conflict_diag['ok'] else 'WARNING'} - {conflict_diag['msg']}")
            print("=" * 60)
        return 0

    song_choices = get_song_choices(force_refresh=True)

    if args.list:
        print_choices_local(song_choices)
        return 0

    if not song_choices and args.song is None:
        print_choices_local(song_choices)
        return 1

    try:
        enable_high_precision_timers()

        if args.song is not None:
            selected_song = resolve_song_selection(args.song, song_choices)
            if selected_song is None:
                return 2

            repeat_count = max(args.repeat, 1)
            for run_index in range(repeat_count):
                if repeat_count > 1:
                    print(f"Run {run_index + 1}/{repeat_count}: {selected_song.stem}")
                if not args.no_clear:
                    clear_terminal()
                result = play_selected_song(selected_song, args.countdown, controls=controls)
                if result == PLAYBACK_QUIT:
                    return 0
                if result == PLAYBACK_SKIPPED:
                    return 0
            return 0

        while True:
            selected_song = prompt_song_selection()
            if selected_song is None:
                return 0

            if not args.no_clear:
                clear_terminal()

            result = play_selected_song(selected_song, args.countdown, controls=controls)
            if result == PLAYBACK_QUIT:
                return 0
            if result == PLAYBACK_SKIPPED:
                time.sleep(0.5)
            else:
                time.sleep(2)

            if not args.no_clear:
                clear_terminal()

    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 130
    finally:
        disable_high_precision_timers()

if __name__ == '__main__':
    raise SystemExit(main())
