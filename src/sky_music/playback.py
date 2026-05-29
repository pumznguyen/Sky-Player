import time
from typing import Tuple, Optional
from sky_music.domain import Song
from sky_music.scheduler_types import KeyAction
from sky_music.backend import InputBackend
from sky_music.telemetry import TelemetryLogger
from sky_music.timing import Clock, Sleeper, PerfCounterClock, RealSleeper, SleepPolicy
from sky_music.focus import FocusGuard, NoopFocusGuard, Win32SkyFocusGuard

# We use standard outputs from UI and main
PLAYBACK_FINISHED = "finished"
PLAYBACK_SKIPPED = "skipped"
PLAYBACK_QUIT = "quit"

class PlaybackEngine:
    """Manages the real-time execution loop of the scheduled KeyActions timeline."""
    def __init__(
        self,
        song: Song,
        actions: Tuple[KeyAction, ...],
        backend: InputBackend,
        controls = None,
        renderer = None,
        telemetry_enabled: bool = False,
        require_focus: bool = True,
        clock: Optional[Clock] = None,
        sleeper: Optional[Sleeper] = None,
        sleep_policy: SleepPolicy = SleepPolicy(),
        focus_guard: Optional[FocusGuard] = None,
        profile_name: str = "balanced",
        tempo_scale: float = 1.0
    ):
        self.song = song
        self.actions = actions
        self.backend = backend
        self.controls = controls
        self.renderer = renderer
        self.telemetry = TelemetryLogger(
            song.name,
            enabled=telemetry_enabled,
            profile_name=profile_name,
            tempo_scale=tempo_scale
        )
        self.require_focus = require_focus
        self.clock = clock if clock is not None else PerfCounterClock()
        self.sleeper = sleeper if sleeper is not None else RealSleeper()
        self.sleep_policy = sleep_policy
        
        # Inject standard FocusGuard depending on requirements
        if focus_guard is None:
            if self.require_focus:
                self.focus_guard: FocusGuard = Win32SkyFocusGuard()
            else:
                self.focus_guard = NoopFocusGuard()
        else:
            self.focus_guard = focus_guard
        
    def play(self) -> str:
        start_perf = self.clock.now_us()
        pause_time_us = 0
        manual_pause_started_us = None
        focus_pause_started_us = None
        
        total_time_us = max(a.at_us for a in self.actions) if self.actions else 0
        total_time_seconds = total_time_us / 1_000_000
        
        # Telemetry diagnostic counters
        late_events_over_2ms = 0
        late_events_over_5ms = 0
        late_events_over_10ms = 0
        max_lateness_us = 0
        
        def get_elapsed_us() -> int:
            now_us = self.clock.now_us()
            elapsed = now_us - start_perf - pause_time_us
            if manual_pause_started_us is not None:
                elapsed -= (now_us - manual_pause_started_us)
            if focus_pause_started_us is not None:
                elapsed -= (now_us - focus_pause_started_us)
            return max(0, elapsed)
            
        def sleep_for_playback(remaining_seconds: float) -> None:
            policy = self.sleep_policy
            if remaining_seconds <= 0:
                return
                
            if remaining_seconds > 0.050:
                # Long sleep: yield fully to the OS
                self.sleeper.sleep(min(policy.poll_s, remaining_seconds - 0.010))
            elif remaining_seconds > 0.005:
                # Medium sleep: minor yield
                self.sleeper.sleep(policy.min_sleep_s)
            else:
                # Tiny sleep / yield zone: yield thread slice
                self.sleeper.sleep(0)
                
        # Main execution loop
        try:
            for idx, action in enumerate(self.actions):
                while True:
                    command = self.controls.poll() if self.controls is not None else None
                    now_us = self.clock.now_us()
                    
                    if command == "quit":
                        if self.renderer:
                            self.renderer.finish(f"Stopped: {self.song.name}")
                        return PLAYBACK_QUIT
                        
                    if command == "skip":
                        if self.renderer:
                            self.renderer.finish(f"Skipped: {self.song.name}")
                        return PLAYBACK_SKIPPED
                        
                    if command == "refocus":
                        self.focus_guard.focus()
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="refocus", force=True)

                    if command == "panic":
                        # Emergency release: release all currently held keys, then continue playback
                        self.backend.release_all()
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="panic", force=True)
                            
                    if command == "pause":
                        if manual_pause_started_us is None:
                            self.backend.release_all()
                            manual_pause_started_us = now_us
                            if self.renderer:
                                self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="paused", force=True)
                        else:
                            pause_time_us += (now_us - manual_pause_started_us)
                            manual_pause_started_us = None
                            if self.renderer:
                                self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="playing", force=True)
                                
                    if manual_pause_started_us is not None:
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="paused")
                        self.sleeper.sleep(self.sleep_policy.poll_s)
                        continue
                        
                    # Check target window focus (Windows-specific check isolated behind FocusGuard)
                    if self.require_focus and not self.focus_guard.is_active():
                        self.backend.release_all()
                        if focus_pause_started_us is None:
                            focus_pause_started_us = self.clock.now_us()
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="focus_lost")
                        self.sleeper.sleep(self.sleep_policy.poll_s)
                        continue
                        
                    if focus_pause_started_us is not None:
                        pause_time_us += (self.clock.now_us() - focus_pause_started_us)
                        focus_pause_started_us = None
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="playing", force=True)
                            
                    elapsed_us = get_elapsed_us()
                    if elapsed_us >= action.at_us:
                        break
                        
                    if self.renderer:
                        self.renderer.render(elapsed_us / 1_000_000, total_time_seconds, self.song.name, status="playing")
                    sleep_for_playback((action.at_us - elapsed_us) / 1_000_000)
                    
                # Execute action
                send_start_us = get_elapsed_us()
                
                if action.kind == "down":
                    self.backend.key_down(action.scan_codes)
                else:
                    self.backend.key_up(action.scan_codes)
                    
                send_end_us = get_elapsed_us()
                send_duration_us = send_end_us - send_start_us
                
                lateness_us = send_start_us - action.at_us
                if lateness_us > 0:
                    max_lateness_us = max(max_lateness_us, lateness_us)
                    if lateness_us > 2000:
                        late_events_over_2ms += 1
                    if lateness_us > 5000:
                        late_events_over_5ms += 1
                    if lateness_us > 10000:
                        late_events_over_10ms += 1

                if self.renderer and hasattr(self.renderer, 'update_counters'):
                    self.renderer.update_counters(max(0, lateness_us))

                # Record telemetry logs
                self.telemetry.record(
                    event_index=idx,
                    kind=action.kind,
                    scheduled_us=action.at_us,
                    actual_us=send_start_us,
                    lateness_us=lateness_us,
                    send_duration_us=send_duration_us,
                    scan_codes=action.scan_codes,
                    reason=action.reason
                )
                
            if self.renderer:
                self.renderer.render(total_time_seconds, total_time_seconds, self.song.name, status="done", force=True)
                self.renderer.finish(f"Finished playing {self.song.name}")
                
            # Log summary diagnostic metrics
            import inputs
            if hasattr(inputs, "PLAYBACK_DEBUG") and inputs.PLAYBACK_DEBUG:
                inputs.debug_log(
                    f"Timing summary (Microsecond Engine): "
                    f"late events over 2ms={late_events_over_2ms}, "
                    f"late events over 5ms={late_events_over_5ms}, "
                    f"late events over 10ms={late_events_over_10ms}, "
                    f"max lateness={max_lateness_us / 1_000_000:.6f}s"
                )
                
            return PLAYBACK_FINISHED
            
        finally:
            self.backend.release_all()
            self.telemetry.record_backend_health(self.backend.get_health())
            self.telemetry.save()
