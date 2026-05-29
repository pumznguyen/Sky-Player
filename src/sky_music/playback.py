import time
from typing import Tuple, Optional
from sky_music.domain import Song
from sky_music.scheduler import KeyAction
from sky_music.backend import InputBackend
from sky_music.telemetry import TelemetryLogger

# We use standard outputs from UI and main
PLAYBACK_FINISHED = "finished"
PLAYBACK_SKIPPED = "skipped"
PLAYBACK_QUIT = "quit"
PLAYBACK_POLL_SECONDS = 0.025

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
        require_focus: bool = True
    ):
        self.song = song
        self.actions = actions
        self.backend = backend
        self.controls = controls
        self.renderer = renderer
        self.telemetry = TelemetryLogger(song.name, enabled=telemetry_enabled)
        self.require_focus = require_focus
        
    def play(self) -> str:
        # Avoid dynamic imports if possible, but keep focus/window primitives handy
        import inputs
        
        start_perf = time.perf_counter()
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
            now_us = int(time.perf_counter() * 1_000_000)
            elapsed = now_us - int(start_perf * 1_000_000) - pause_time_us
            if manual_pause_started_us is not None:
                elapsed -= (now_us - manual_pause_started_us)
            if focus_pause_started_us is not None:
                elapsed -= (now_us - focus_pause_started_us)
            return max(0, elapsed)
            
        def sleep_for_playback(remaining_seconds: float) -> None:
            if remaining_seconds > 0.05:
                time.sleep(min(PLAYBACK_POLL_SECONDS, max(0.001, remaining_seconds - 0.01)))
            elif remaining_seconds > 0.005:
                time.sleep(0.001)
            else:
                time.sleep(0)
                
        # Main execution loop
        try:
            for idx, action in enumerate(self.actions):
                while True:
                    command = self.controls.poll() if self.controls is not None else None
                    now_us = int(time.perf_counter() * 1_000_000)
                    
                    if command == "quit":
                        if self.renderer:
                            self.renderer.finish(f"Stopped: {self.song.name}")
                        return PLAYBACK_QUIT
                        
                    if command == "skip":
                        if self.renderer:
                            self.renderer.finish(f"Skipped: {self.song.name}")
                        return PLAYBACK_SKIPPED
                        
                    if command == "refocus":
                        inputs.focusWindow()
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="refocus", force=True)
                            
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
                        time.sleep(PLAYBACK_POLL_SECONDS)
                        continue
                        
                    # Check target window focus (Windows-specific check)
                    if self.require_focus and hasattr(inputs, "is_sky_active") and not inputs.is_sky_active():
                        self.backend.release_all()
                        if focus_pause_started_us is None:
                            focus_pause_started_us = int(time.perf_counter() * 1_000_000)
                        if self.renderer:
                            self.renderer.render(get_elapsed_us() / 1_000_000, total_time_seconds, self.song.name, status="focus_lost")
                        time.sleep(PLAYBACK_POLL_SECONDS)
                        continue
                        
                    if focus_pause_started_us is not None:
                        pause_time_us += (int(time.perf_counter() * 1_000_000) - focus_pause_started_us)
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
                
            # Log summary diagnostic metrics to standard inputs debug_log
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
            self.telemetry.save()
