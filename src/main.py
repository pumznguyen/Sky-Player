import argparse
import sys
import time
from pathlib import Path

# Import từ các mô-đun chuyên biệt
import inputs
from inputs import (
    enable_high_precision_timers,
    disable_high_precision_timers,
    wait_seconds,
    send_scan_code_batch,
    release_active_keys,
    focusWindow,
    get_sky_window,
    is_sky_active
)
from scheduler import (
    MIN_KEY_HOLD_SECONDS,
    REPEAT_RELEASE_GAP_SECONDS,
    key_maps,
    NOTE_SCAN_CODES,
    build_note_scan_codes,
    build_playback_events
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
    load_song_data,
    countdown_before_playback,
    ensure_sky_ready
)

PLAYBACK_DEBUG = False
DEBUG_LOG_PATH = None
DEBUG_START_PERF = None
DEBUG_LOG_BUFFER = []

def init_debug_log():
    global DEBUG_LOG_PATH, DEBUG_START_PERF
    DEBUG_START_PERF = time.perf_counter()
    debug_log_dir = Path("logs")
    debug_log_dir.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_PATH = debug_log_dir / f"playback_debug_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with DEBUG_LOG_PATH.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debug playback log started\n")

def debug_log(message):
    if not PLAYBACK_DEBUG:
        return
    now = time.perf_counter()
    rel = 0.0 if DEBUG_START_PERF is None else now - DEBUG_START_PERF
    DEBUG_LOG_BUFFER.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')} +{rel:.6f}s] {message}")

def flush_debug_log():
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

def play_music(song_data, controls=None):
    global DEBUG_START_PERF
    DEBUG_START_PERF = time.perf_counter()

    song = song_data[0]
    scan_code_batches = song["__scan_code_batches"]
    playback_meta = build_playback_events(scan_code_batches)
    playback_events = playback_meta["events"]
    start_time = time.perf_counter()
    pause_time = 0.0
    manual_pause_started_at = None
    focus_pause_started_at = None
    total_time = song["__total_time"]
    song_name = song["__name"]
    active_down_keys = set()
    active_down_started_at = {}
    renderer = ProgressRenderer(controls)
    delayed_keyups = 0
    late_events_over_2ms = 0
    late_events_over_5ms = 0
    late_events_over_10ms = 0
    forced_repeat_releases = 0
    skipped_stale_keyups = 0
    short_hold_released = 0
    max_lateness = 0.0

    def get_elapsed_time():
        now = time.perf_counter()
        elapsed = now - start_time - pause_time
        if manual_pause_started_at is not None:
            elapsed -= now - manual_pause_started_at
        if focus_pause_started_at is not None:
            elapsed -= now - focus_pause_started_at
        return max(0.0, elapsed)

    def sleep_for_playback(remaining_time):
        if remaining_time > 0.05:
            time.sleep(min(PLAYBACK_POLL_SECONDS, max(0.001, remaining_time - 0.01)))
        elif remaining_time > 0.005:
            time.sleep(0.001)
        else:
            time.sleep(0)

    debug_log(
        f"Start song: {song_name} | batches={len(scan_code_batches)} | events={len(playback_events)}"
    )

    renderer.render(0.0, total_time, song_name, status="playing", force=True)

    try:
        for current_time, _priority, current_scan_codes, is_key_up, enforce_min_hold in playback_events:
            while True:
                command = controls.poll() if controls is not None else None
                now = time.perf_counter()

                if command == "quit":
                    renderer.finish(f"Stopped: {song_name}")
                    return PLAYBACK_QUIT

                if command == "skip":
                    renderer.finish(f"Skipped: {song_name}")
                    return PLAYBACK_SKIPPED

                if command == "refocus":
                    focusWindow()
                    renderer.render(get_elapsed_time(), total_time, song_name, status="refocus", force=True)

                if command == "pause":
                    if manual_pause_started_at is None:
                        release_active_keys(active_down_keys, active_down_started_at)
                        manual_pause_started_at = now
                        renderer.render(get_elapsed_time(), total_time, song_name, status="paused", force=True)
                        if PLAYBACK_DEBUG:
                            debug_log("[control] manual pause")
                    else:
                        pause_time += now - manual_pause_started_at
                        manual_pause_started_at = None
                        renderer.render(get_elapsed_time(), total_time, song_name, status="playing", force=True)
                        if PLAYBACK_DEBUG:
                            debug_log("[control] manual resume")

                if manual_pause_started_at is not None:
                    renderer.render(get_elapsed_time(), total_time, song_name, status="paused")
                    time.sleep(PLAYBACK_POLL_SECONDS)
                    continue

                if not is_sky_active():
                    release_active_keys(active_down_keys, active_down_started_at)
                    flush_debug_log()

                    if focus_pause_started_at is None:
                        focus_pause_started_at = time.perf_counter()
                        if PLAYBACK_DEBUG:
                            debug_log("[window] focus lost, playback paused")

                    renderer.render(get_elapsed_time(), total_time, song_name, status="focus_lost")
                    time.sleep(PLAYBACK_POLL_SECONDS)
                    continue

                if focus_pause_started_at is not None:
                    pause_time += time.perf_counter() - focus_pause_started_at
                    focus_pause_started_at = None
                    renderer.render(get_elapsed_time(), total_time, song_name, status="playing", force=True)
                    if PLAYBACK_DEBUG:
                        debug_log("[window] focus restored, playback resumed")

                elapsed_time = get_elapsed_time()
                if elapsed_time >= current_time:
                    break

                renderer.render(elapsed_time, total_time, song_name, status="playing")
                sleep_for_playback(current_time - elapsed_time)

            lateness = elapsed_time - current_time
            if lateness > 0:
                max_lateness = max(max_lateness, lateness)
                if lateness > 0.002:
                    late_events_over_2ms += 1
                if lateness > 0.005:
                    late_events_over_5ms += 1
                if lateness > 0.010:
                    late_events_over_10ms += 1
                    if PLAYBACK_DEBUG:
                        debug_log(
                            f"[timing] late event by {lateness:.4f}s | "
                            f"key_up={is_key_up} | scan_codes={current_scan_codes}"
                        )

            if is_key_up:
                current_scan_codes = tuple(
                    scan_code for scan_code in current_scan_codes
                    if scan_code in active_down_keys
                )
                if not current_scan_codes:
                    skipped_stale_keyups += 1
                    if PLAYBACK_DEBUG:
                        debug_log("[input] skipped stale key-up")
                    continue

                if enforce_min_hold:
                    earliest_release_time = max(
                        active_down_started_at.get(scan_code, elapsed_time) + MIN_KEY_HOLD_SECONDS
                        for scan_code in current_scan_codes
                    )
                    if elapsed_time < earliest_release_time:
                        delay = earliest_release_time - elapsed_time
                        delayed_keyups += 1
                        if PLAYBACK_DEBUG:
                            debug_log(f"[timing] delayed key-up by {delay:.4f}s")
                        wait_seconds(delay)
                else:
                    actual_holds = [
                        elapsed_time - active_down_started_at.get(scan_code, elapsed_time)
                        for scan_code in current_scan_codes
                    ]
                    if any(h < MIN_KEY_HOLD_SECONDS for h in actual_holds):
                        short_hold_released += 1
                        if PLAYBACK_DEBUG:
                            debug_log(f"[input] allowed short-hold release below min-hold: {actual_holds}")
            else:
                repeated_scan_codes = tuple(
                    scan_code for scan_code in current_scan_codes
                    if scan_code in active_down_keys
                )
                if repeated_scan_codes:
                    forced_repeat_releases += 1
                    if PLAYBACK_DEBUG:
                        debug_log(f"[input] forced release before repeat: {repeated_scan_codes}")
                    send_scan_code_batch(repeated_scan_codes, key_up=True)
                    active_down_keys.difference_update(repeated_scan_codes)
                    for scan_code in repeated_scan_codes:
                        active_down_started_at.pop(scan_code, None)
                    wait_seconds(REPEAT_RELEASE_GAP_SECONDS)

            send_scan_code_batch(current_scan_codes, key_up=is_key_up)
            actual_elapsed_time = get_elapsed_time()
            if is_key_up:
                active_down_keys.difference_update(current_scan_codes)
                for scan_code in current_scan_codes:
                    active_down_started_at.pop(scan_code, None)
            else:
                active_down_keys.update(current_scan_codes)
                for scan_code in current_scan_codes:
                    active_down_started_at[scan_code] = actual_elapsed_time

        renderer.render(total_time, total_time, song_name, status="done", force=True)
        renderer.finish(f"Finished playing {song_name}")
        if PLAYBACK_DEBUG:
            debug_log(
                f"Timing summary: compressed holds={playback_meta['compressed_holds']}, "
                f"impossible same-key repeats={playback_meta.get('impossible_same_key_repeats', 0)}, "
                f"delayed key-ups={delayed_keyups}, "
                f"late events over 2ms={late_events_over_2ms}, "
                f"late events over 5ms={late_events_over_5ms}, "
                f"late events over 10ms={late_events_over_10ms}, "
                f"max lateness={max_lateness:.6f}s, "
                f"forced repeat releases={forced_repeat_releases}, "
                f"skipped stale key-ups={skipped_stale_keyups}, "
                f"short-holds released={short_hold_released}"
            )
        return PLAYBACK_FINISHED
    finally:
        debug_log(f"End song: {song_name}")
        release_active_keys(active_down_keys, active_down_started_at)
        flush_debug_log()

def play_selected_song(selected_song, countdown_seconds, controls=None):
    song_data = load_song_data(selected_song)
    if song_data is None:
        return PLAYBACK_QUIT
    if not ensure_sky_ready():
        return PLAYBACK_QUIT
    if controls is not None and controls.enabled:
        print(f"Controls: {controls.hint()}")
    countdown_before_playback(countdown_seconds)
    return play_music(song_data, controls=controls)

def run_doctor(scan_code_mode):
    print("Terminal doctor")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    print(f"Songs dir: {SONG_DIR.resolve()}")
    print(f"Supported files: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    song_choices = get_song_choices(force_refresh=True)
    print(f"Detected songs: {len(song_choices)}")
    if song_choices:
        print(f"First song: {song_choices[0].name}")

    try:
        test_scan_codes = build_note_scan_codes(key_maps, scan_code_mode=scan_code_mode)
        print(f"Key mapping: OK ({len(test_scan_codes)} mapped keys)")
    except Exception as exc:
        print(f"Key mapping: FAILED ({exc})")

    try:
        detected_window = get_sky_window()
        print(f"Sky window: {'OK' if detected_window else 'NOT FOUND'}")
    except Exception as exc:
        print(f"Sky window check: FAILED ({exc})")

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
        help="check songs folder, key mapping, and Sky window detection",
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
    return parser

def configure_from_args(args):
    global PLAYBACK_DEBUG, DEBUG_LOG_PATH
    import inputs
    import songs

    songs.SONG_DIR = args.songs_dir
    PLAYBACK_DEBUG = args.debug_playback
    inputs.PLAYBACK_DEBUG = args.debug_playback

    if PLAYBACK_DEBUG:
        init_debug_log()

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

    NOTE_SCAN_CODES.clear()
    NOTE_SCAN_CODES.update(build_note_scan_codes(key_maps, scan_code_mode=args.scan_code_mode))

def build_playback_controls(args):
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

def prompt_song_selection():
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

def print_choices_local(song_choices):
    if not song_choices:
        print(f"No songs found in: {SONG_DIR.resolve()}")
        print(f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return
    print("Songs:")
    for index, path in enumerate(song_choices, start=1):
        print(f"  {index:>2}) {path.stem}")

def main():
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

    if args.doctor:
        run_doctor(args.scan_code_mode)
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
