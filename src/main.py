import argparse
import sys
import time
from pathlib import Path

# Import từ các mô-đun chuyên biệt
import inputs
from sky_music.config import load_config, save_config, apply_config_defaults
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
    ensure_sky_ready,
    SongPickerResult,
)

PLAYBACK_DEBUG = False
CURRENT_SCAN_CODE_MODE = "physical"
DEBUG_LOG_PATH = None
DEBUG_START_PERF = None
DEBUG_LOG_BUFFER = []
TIMING_POLICY = None
TELEMETRY_CSV_ENABLED = False
DRY_RUN_MODE = False
TEMPO_SCALE = 1.0
TIMING_PROFILE_NAME = "balanced"
VERBOSE_HUD = False

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

def _recommended_profile(severity: str, has_same_key_repeats: bool, high_polyphony: bool) -> str:
    """Suggest a timing profile name based on risk characteristics."""
    if severity == "high":
        if has_same_key_repeats:
            return "dense-safe"
        return "remote-safe"
    if severity == "medium":
        if high_polyphony:
            return "remote-safe"
        return "balanced"
    return "balanced"


def _handle_risk_analysis(report, song, is_dry_run: bool, controls, policy_override_fn=None) -> tuple[bool, str | None, float | None]:
    """Display risk analysis, prompt user for action if severity is medium/high.

    Returns (should_continue, new_profile_name_or_None, new_tempo_scale_or_None).
    """
    from sky_music.analyzer import ScheduleRiskReport  # type: ignore[attr-defined]
    severity = report.severity.upper()
    recommended = _recommended_profile(
        report.severity,
        has_same_key_repeats=report.impossible_same_key_repeats > 0,
        high_polyphony=report.max_polyphony >= 5,
    )

    print()
    print(f"  ┌─ Schedule Risk: {severity} " + "─" * max(0, 38 - len(severity)))
    for rec in report.recommendations:
        print(f"  │  * {rec}")
    print(f"  │  Recommended profile: {recommended}")
    print(f"  └{'─' * 44}")
    print()

    if is_dry_run:
        # In dry-run mode just show the warning, don't block
        return True, None, None

    print("  What would you like to do?")
    print(f"  [1] Switch to '{recommended}' profile")
    print( "  [2] Scale tempo down to 0.92x")
    print( "  [3] Dry-run first (simulate, no keystrokes)")
    print( "  [4] Proceed with current settings")
    print( "  [5] Cancel")
    print()

    try:
        choice = input("  Choice [1-5]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return False, None, None

    if choice == "1":
        print(f"  → Switched to profile: {recommended}")
        return True, recommended, None
    elif choice == "2":
        print( "  → Tempo scaled to 0.92x")
        return True, None, 0.92
    elif choice == "3":
        print( "  → Running dry-run simulation first...")
        return True, None, None  # caller handles dry-run flag
    elif choice == "5":
        return False, None, None
    else:
        print( "  → Proceeding with current settings.")
        return True, None, None


def _mini_preflight(is_dry_run: bool) -> bool:
    """Preflight check before real playback — uniform box-style output."""
    if is_dry_run:
        return True

    import sky_music.doctor as doctor
    checks: list[tuple[bool, str]] = []

    # 1. Sky window
    win = doctor.check_sky_window()
    checks.append((win["ok"], "Sky window detected" if win["ok"] else f"Sky not found: {win['msg']}"))
    if not win["ok"]:
        print()
        print("  ╭─ Readiness ────────────────────────────────────────────────")
        print(f"  │  ✗ Sky not found: {win['msg']}")
        print(  "  ╰" + "─" * 56)
        while True:
            try:
                choice = input("  Sky not found. [R] retry  [D] dry-run  [Enter] cancel: ").strip().casefold()
            except (EOFError, KeyboardInterrupt):
                return False
            if choice == "r":
                win = doctor.check_sky_window()
                if win["ok"]:
                    checks[0] = (True, "Sky window detected")
                    break
                print(f"  ✗ Still not found: {win['msg']}")
            elif choice == "d":
                print("  → Use --dry-run to simulate without Sky.")
                return False
            else:
                return False

    # 2. Focus
    import inputs as _inputs
    _inputs.focusWindow()
    checks.append((True, "Focus requested"))

    # 3. Timer
    timer = doctor.check_timer_resolution()
    checks.append((timer["ok"], "High-precision timers active" if timer["ok"] else timer["msg"]))

    # 4. Key conflicts
    keys = doctor.check_physical_keys_held()
    checks.append((keys["ok"], "No note keys held" if keys["ok"] else f"Keys held: {', '.join(keys.get('held_keys', []))}"))

    # Render uniform box
    print()
    print("  ╭─ Readiness ────────────────────────────────────────────────")
    row: list[str] = []
    for ok, msg in checks:
        icon = "✓" if ok else "⚠"
        row.append(f"{icon} {msg}")
        if len(row) == 2:
            print(f"  │  {row[0]:<28}  {row[1]}")
            row = []
    if row:
        print(f"  │  {row[0]}")
    print(  "  ╰" + "─" * 56)
    print()
    return True


def _print_post_run_report(engine, profile_name: str, tempo_scale: float) -> None:
    """Print a readable post-run timing/backend summary from the engine's telemetry."""
    summary = engine.telemetry.get_summary()
    if not summary:
        return

    lat = summary.get("lateness_us", {})
    snd = summary.get("send_duration_us", {})
    hld = summary.get("note_hold_duration_us", {})
    bk = summary.get("backend", {})
    total = summary.get("total_events", 0)

    print()
    print("  ┌─ Post-run Report " + "─" * 41)
    print(f"  │  Profile: {profile_name}  |  Tempo: {tempo_scale:.2f}x  |  Events: {total}")
    print(f"  │  Lateness     p50={lat.get('p50_us',0):.0f}µs  p95={lat.get('p95_us',0):.0f}µs  p99={lat.get('p99_us',0):.0f}µs  max={lat.get('max_us',0):.0f}µs")
    print(f"  │  Late >2ms={lat.get('over_2ms',0)}  >5ms={lat.get('over_5ms',0)}  >10ms={lat.get('over_10ms',0)}")
    print(f"  │  Send dur    p95={snd.get('p95_us',0):.0f}µs  |  Hold avg={hld.get('avg_us',0)/1000:.1f}ms")
    failures = bk.get("panic_release_failures", 0)
    stuck = bk.get("failed_release_keys_final", [])
    if failures or stuck:
        print(f"  │  Backend: ⚠ {failures} panic failure(s), stuck keys: {stuck}")
    else:
        print( "  │  Backend: healthy (✓ no stuck keys)")

    # Quality recommendation
    p99 = lat.get("p99_us", 0)
    over_10ms = lat.get("over_10ms", 0)
    if failures or stuck:
        print( "  │  ⚠ Recommendation: Stuck keys detected — run --doctor before next playback.")
    elif over_10ms > 5 or p99 > 15000:
        print(f"  │  Recommendation: Latency high (p99={p99/1000:.1f}ms). Try --timing-profile dense-safe or lower tempo.")
    elif over_10ms > 0 or p99 > 8000:
        print(f"  │  Recommendation: Occasional late events (p99={p99/1000:.1f}ms). remote-safe or reduce --tempo-scale slightly.")
    else:
        print( "  │  Timing quality: good ✓")
    print(  "  └" + "─" * 57)
    print()


def play_selected_song(
    selected_song: Path,
    countdown_seconds: int,
    controls: PlaybackControls | None = None,
    force_dry_run: bool = False,
    force_profile: str | None = None,
    force_tempo: float | None = None,
) -> str:
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
    # Picker decision overrides global config (advisory-only flow)
    current_profile = force_profile if force_profile is not None else TIMING_PROFILE_NAME
    current_tempo   = force_tempo   if force_tempo   is not None else TEMPO_SCALE

    # Build scheduled actions using specified TimingPolicy and selected mode
    sched_meta = build_key_actions(song, policy=TIMING_POLICY, scan_code_mode=CURRENT_SCAN_CODE_MODE, tempo_scale=current_tempo)
    actions = sched_meta.actions

    # Pre-playback schedule risk analysis (advisory only — do NOT auto-apply)
    from sky_music.analyzer import analyze_schedule
    report = analyze_schedule(sched_meta)

    # If picker already decided (force_profile/tempo supplied), skip the prompt
    if report.severity != "low" and force_profile is None and force_tempo is None:
        should_continue, new_profile, new_tempo = _handle_risk_analysis(
            report, song, is_dry_run, controls
        )
        if not should_continue:
            return PLAYBACK_QUIT
        if new_profile is not None and new_profile != current_profile:
            # Rebuild schedule with the switched profile
            from sky_music.scheduler import TimingPolicy
            profile_map = {
                "local-precise": TimingPolicy.local_precise,
                "remote-safe": TimingPolicy.remote_safe,
                "dense-safe": TimingPolicy.dense_safe,
            }
            if new_profile in profile_map:
                new_policy = profile_map[new_profile]()
            else:
                new_policy = TIMING_POLICY
            sched_meta = build_key_actions(song, policy=new_policy, scan_code_mode=CURRENT_SCAN_CODE_MODE, tempo_scale=current_tempo)
            actions = sched_meta.actions
            current_profile = new_profile
        if new_tempo is not None:
            sched_meta = build_key_actions(song, policy=TIMING_POLICY, scan_code_mode=CURRENT_SCAN_CODE_MODE, tempo_scale=new_tempo)
            actions = sched_meta.actions
            current_tempo = new_tempo

    # Preflight check and window readiness
    if not _mini_preflight(is_dry_run):
        return PLAYBACK_QUIT

    # Check window/readiness only if we are NOT running dry-run mode
    if not is_dry_run:
        if controls is not None and controls.enabled:
            print(f"  Controls: {controls.hint()}")
        countdown_before_playback(countdown_seconds)
    else:
        print(f"[simulation] DRY-RUN enabled. Simulating playback of {song.name}...")

    backend = DryRunBackend() if is_dry_run else WinSendInputBackend()
    renderer = ProgressRenderer(
        controls,
        verbose=VERBOSE_HUD,
        profile_name=current_profile,
        tempo_scale=current_tempo,
    )
    
    engine = PlaybackEngine(
        song=song,
        actions=actions,
        backend=backend,
        controls=controls,
        renderer=renderer,
        telemetry_enabled=TELEMETRY_CSV_ENABLED or PLAYBACK_DEBUG or force_dry_run,
        require_focus=not is_dry_run,
        profile_name=current_profile,
        tempo_scale=current_tempo
    )
    result = engine.play()
    # P3: post-run summary
    _print_post_run_report(engine, current_profile, current_tempo)
    return result


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Play Sky song files from the terminal.",
    )

    # ── Song Selection ────────────────────────────────────────────────────────
    sel = parser.add_argument_group("Song selection")
    sel.add_argument(
        "--song",
        help="play a song by number, exact name, partial name, or file path",
    )
    sel.add_argument(
        "--list",
        action="store_true",
        help="list available songs and exit",
    )
    sel.add_argument(
        "--songs-dir",
        type=Path,
        default=SONG_DIR,
        help="folder containing .json/.skysheet files",
    )
    sel.add_argument(
        "--countdown",
        type=int,
        default=3,
        help="seconds to wait before playback starts (default: 3)",
    )
    sel.add_argument(
        "--repeat",
        type=int,
        default=1,
    )
    # ── Playback Timing ───────────────────────────────────────────────────────
    timing = parser.add_argument_group("Playback timing")
    timing.add_argument(
        "--timing-profile",
        choices=["fast", "balanced", "conservative", "local-precise", "remote-safe", "dense-safe"],
        default="balanced",
        help=(
            "Timing profile: "
            "local-precise (low latency), "
            "remote-safe (listener quality), "
            "dense-safe (many chords/repeats), "
            "fast (experimental), "
            "balanced (default), "
            "conservative (safe/slower)"
        ),
    )
    timing.add_argument(
        "--tempo-scale",
        type=float,
        default=1.0,
        help="Scale playback tempo: 1.2 = 20%% faster, 0.8 = 20%% slower (default: 1.0)",
    )
    timing.add_argument(
        "--hold-ms",
        type=int,
        help="Override key hold duration in ms (overrides profile)",
    )
    timing.add_argument(
        "--min-hold-ms",
        type=int,
        help="Override minimum key hold duration in ms (overrides profile)",
    )
    timing.add_argument(
        "--release-gap-ms",
        type=int,
        help="Override release gap in ms (overrides profile)",
    )
    timing.add_argument(
        "--repeat-release-gap-ms",
        type=int,
        help="Override same-key repeat gap in ms (overrides profile)",
    )
    timing.add_argument(
        "--scan-code-mode",
        choices=["physical", "mapped"],
        default="physical",
        help="physical = fixed QWERTY scan codes (default), mapped = OS keyboard layout",
    )

    # ── Runtime Controls ──────────────────────────────────────────────────────
    ctrl = parser.add_argument_group("Runtime controls (hotkeys during playback)")
    ctrl.add_argument(
        "--pause-key",
        default="f8",
        help="pause/resume hotkey, e.g. f8 or ctrl+p (default: f8)",
    )
    ctrl.add_argument(
        "--skip-key",
        default="f9",
        help="skip current song hotkey (default: f9)",
    )
    ctrl.add_argument(
        "--quit-key",
        default="f10",
        help="quit playback hotkey (default: f10; Esc not recommended — game may intercept it)",
    )
    ctrl.add_argument(
        "--refocus-key",
        default="f6",
        help="bring Sky window to foreground hotkey (default: f6)",
    )
    ctrl.add_argument(
        "--panic-key",
        default="ctrl+alt+backspace",
        help="emergency release all keys without stopping playback (default: ctrl+alt+backspace)",
    )
    ctrl.add_argument(
        "--disable-hotkeys",
        action="store_true",
        help="disable all runtime hotkeys; use Ctrl+C only",
    )
    ctrl.add_argument(
        "--allow-note-hotkeys",
        action="store_true",
        help="allow hotkeys that overlap with note keys (not recommended)",
    )

    # ── Safety & Diagnostics ──────────────────────────────────────────────────
    diag = parser.add_argument_group("Safety and diagnostics")
    diag.add_argument(
        "--doctor",
        action="store_true",
        help="run full readiness check (Sky window, timers, layout, key conflicts)",
    )
    diag.add_argument(
        "--doctor-timing",
        action="store_true",
        help="check high-precision multimedia timer subsystem only",
    )
    diag.add_argument(
        "--doctor-input",
        action="store_true",
        help="check keyboard layout mapping and physically held note keys only",
    )
    diag.add_argument(
        "--sky-process-names",
        default="Sky.exe,Sky Children of the Light.exe",
        help="comma-separated Sky executable names to match (default: Sky.exe,...)",
    )
    diag.add_argument(
        "--allow-title-fallback",
        action="store_true",
        help="allow window title matching when process verification fails",
    )

    # ── Telemetry ─────────────────────────────────────────────────────────────
    telem = parser.add_argument_group("Telemetry")
    telem.add_argument(
        "--debug-csv",
        action="store_true",
        help="write per-event timing CSV + summary JSON to logs/ after each playback",
    )
    telem.add_argument(
        "--debug-playback",
        action="store_true",
        help="write verbose playback debug log to logs/",
    )
    telem.add_argument(
        "--dry-run",
        action="store_true",
        help="simulate playback in memory without sending any keystrokes (timing diagnosis)",
    )
    telem.add_argument(
        "--inspect-telemetry",
        help="read and summarize telemetry from a .summary.json file or logs/ directory and exit",
    )

    # ── Display ───────────────────────────────────────────────────────────────
    disp = parser.add_argument_group("Display")
    disp.add_argument(
        "--theme",
        choices=["aurora", "minimalist", "slate", "cyberpunk", "classic"],
        default=None,
        help="song picker TUI theme (default: saved or aurora)",
    )
    disp.add_argument(
        "--no-clear",
        action="store_true",
        help="do not clear the terminal between songs",
    )
    disp.add_argument(
        "--verbose-hud",
        action="store_true",
        help="show detailed live timing/backend stats during playback (2-line HUD)",
    )

    return parser

def configure_from_args(args: argparse.Namespace) -> None:
    global PLAYBACK_DEBUG, DEBUG_LOG_PATH, CURRENT_SCAN_CODE_MODE, TIMING_POLICY, TELEMETRY_CSV_ENABLED, DRY_RUN_MODE, TEMPO_SCALE, TIMING_PROFILE_NAME, VERBOSE_HUD
    import inputs
    import songs
    from sky_music.scheduler import TimingPolicy

    CURRENT_SCAN_CODE_MODE = args.scan_code_mode
    songs.SONG_DIR = args.songs_dir
    PLAYBACK_DEBUG = args.debug_playback
    inputs.PLAYBACK_DEBUG = args.debug_playback
    TELEMETRY_CSV_ENABLED = args.debug_csv
    DRY_RUN_MODE = args.dry_run
    TEMPO_SCALE = args.tempo_scale
    TIMING_PROFILE_NAME = args.timing_profile
    VERBOSE_HUD = args.verbose_hud

    if PLAYBACK_DEBUG:
        init_debug_log()

    # Determine base TimingPolicy from profile
    profile = args.timing_profile.lower().replace("-", "_")
    if profile == "local_precise":
        policy = TimingPolicy.local_precise()
    elif profile == "remote_safe":
        policy = TimingPolicy.remote_safe()
    elif profile == "dense_safe":
        policy = TimingPolicy.dense_safe()
    elif profile == "fast":
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
            panic=parse_hotkey(args.panic_key),
            enabled=False,
        )

    controls = PlaybackControls(
        pause=parse_hotkey(args.pause_key),
        skip=parse_hotkey(args.skip_key),
        quit=parse_hotkey(args.quit_key),
        refocus=parse_hotkey(args.refocus_key),
        panic=parse_hotkey(args.panic_key),
    )

    conflicting = [
        ("pause", controls.pause),
        ("skip", controls.skip),
        ("quit", controls.quit),
        ("refocus", controls.refocus),
        # panic always has modifiers, no need to check note conflicts
    ]
    unsafe = [f"{name}={hotkey.display}" for name, hotkey in conflicting if hotkey_conflicts_with_note_keys(hotkey)]
    if unsafe and not args.allow_note_hotkeys:
        raise ValueError(
            "Hotkey overlaps with note keys: "
            + ", ".join(unsafe)
            + ". Use Ctrl/Alt/Shift, a function key, or pass --allow-note-hotkeys if you accept the risk."
        )
    return controls

def prompt_song_selection(
    profile: str = "balanced",
    tempo: float = 1.0,
    dry_run: bool = False,
) -> "songs.SongPickerResult | None":
    import songs
    if songs.HAS_PROMPT_TOOLKIT:
        return songs.choose_song_interactively(
            initial_profile=profile,
            initial_tempo=tempo,
            initial_dry_run=dry_run,
        )

    # Fallback CLI mode (no prompt_toolkit)
    song_choices = get_song_choices(force_refresh=True)
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
            return songs.SongPickerResult(
                song_path=selected_song,
                action="dry_run" if dry_run else "play",
                profile_name=profile,
                tempo_scale=tempo,
            )
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

    # P4: Load user config and apply saved defaults (CLI flags override these)
    user_cfg = load_config()
    apply_config_defaults(args, user_cfg)

    configure_from_args(args)
    try:
        controls = build_playback_controls(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.inspect_telemetry is not None:
        from sky_music.telemetry import inspect_telemetry_report
        inspect_telemetry_report(args.inspect_telemetry)
        return 0

    if args.doctor or args.doctor_timing or args.doctor_input:
        import sky_music.doctor as doctor
        if args.doctor:
            doctor.run_all_doctor_checks()
        elif args.doctor_timing:
            print("=" * 60)
            print("         SKY MUSIC PLAYER — TIMING CHECK")
            print("=" * 60)
            diag = doctor.check_timer_resolution()
            print(f"Status: {'OK' if diag['ok'] else 'FAILED'}\nDetails: {diag['msg']}")
            print("=" * 60)
        elif args.doctor_input:
            print("=" * 60)
            print("         SKY MUSIC PLAYER — INPUT CHECK")
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
            picker_result = prompt_song_selection(
                profile=TIMING_PROFILE_NAME,
                tempo=TEMPO_SCALE,
                dry_run=DRY_RUN_MODE,
            )
            if picker_result is None:
                return 0

            if not args.no_clear:
                clear_terminal()

            force_dry = (picker_result.action == "dry_run")
            result = play_selected_song(
                picker_result.song_path,
                args.countdown,
                controls=controls,
                force_dry_run=force_dry,
                force_profile=picker_result.profile_name,
                force_tempo=picker_result.tempo_scale,
            )
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
