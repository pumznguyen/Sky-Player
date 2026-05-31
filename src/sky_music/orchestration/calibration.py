from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class CalibrationInput:
    profile_name: str
    tempo_scale: float
    fps: int
    p95_lateness_us: int
    p99_lateness_us: int
    p95_send_duration_us: int
    late_over_10ms: int
    impossible_same_key_repeats: int
    risky_same_key_repeats: int
    failed_release_count: int

@dataclass(frozen=True, slots=True)
class CalibrationRecommendation:
    profile_name: str
    tempo_scale: float
    input_lead_us: int
    hold_us: int
    reason: str
    severity: Literal["ok", "moderate", "severe"]

def calibrate_profile(inp: CalibrationInput) -> CalibrationRecommendation:
    """
    Analyzes high-precision telemetry loops and returns targeted calibration parameter proposals.
    """
    from sky_music.config import load_config
    from sky_music.domain.scheduler_types import FrameTimingPolicy, TimingPolicy

    fps = inp.fps if inp.fps > 0 else 60
    frame_us = round(1_000_000 / fps)
    cfg = load_config()
    
    # 1. Input Lead calibration formula
    recommended_lead = inp.p95_lateness_us + inp.p95_send_duration_us + int(frame_us * 0.5)
    
    # Clamp based on FPS targets to prevent excessive lag or premature key releases
    if inp.fps == 120:
        recommended_lead = max(4000, min(14000, recommended_lead))
    elif inp.fps == 60:
        recommended_lead = max(8000, min(24000, recommended_lead))
    elif inp.fps == 30:
        recommended_lead = max(16000, min(45000, recommended_lead))
    else:
        recommended_lead = max(6000, min(30000, recommended_lead))
        
    p99 = inp.p99_lateness_us
    late_10ms = inp.late_over_10ms
    
    # 2. Timing Profile and Tempo Scale calibration decision tree
    if inp.failed_release_count > 0 or inp.impossible_same_key_repeats > 5 or p99 > 15000 or late_10ms > 5:
        severity = "severe"
        rec_profile = "remote-safe" if inp.fps <= 30 else "dense-safe"
        rec_tempo = round(inp.tempo_scale * 0.90, 2)
        reason = f"Severe timing jitter detected (p99={p99/1000:.1f}ms, late >10ms count={late_10ms}). Recommend safe/dense playback and scaling down tempo."
    elif p99 > 8000 or late_10ms > 0:
        severity = "moderate"
        rec_profile = "balanced"
        rec_tempo = round(inp.tempo_scale * 0.95, 2)
        reason = f"Moderate timing latency detected (p99={p99/1000:.1f}ms). Recommend balanced profiles and slight tempo reduction."
    elif p99 < 3000:
        severity = "ok"
        rec_profile = "local-precise"
        rec_tempo = inp.tempo_scale
        reason = f"Excellent timing performance (p99={p99/1000:.1f}ms). High precision profiles can be safely used."
    else:
        severity = "ok"
        rec_profile = inp.profile_name
        rec_tempo = inp.tempo_scale
        reason = "Good timing performance. Current parameters are well-calibrated."

    # 3. Hold duration via the same FrameTimingPolicy path as playback scheduling
    base = TimingPolicy.from_profile_name(rec_profile, cfg)
    effective = FrameTimingPolicy.from_timing_policy(
        base,
        fps=inp.fps if inp.fps > 0 else None,
        **cfg.frame_timing.as_policy_kwargs(),
    )
    recommended_hold = effective.hold_us
    recommended_lead = max(recommended_lead, effective.input_lead_us)

    return CalibrationRecommendation(
        profile_name=rec_profile,
        tempo_scale=rec_tempo,
        input_lead_us=recommended_lead,
        hold_us=recommended_hold,
        reason=reason,
        severity=severity
    )


def calibration_input_from_summary(summary: dict) -> CalibrationInput:
    """Build CalibrationInput from a telemetry *.summary.json payload."""
    lat = summary.get("lateness_us", {})
    dur = summary.get("send_duration_us", {})
    backend = summary.get("backend", {})
    fps_val = int(summary.get("fps") or 60)
    sched = summary.get("schedule", {})

    return CalibrationInput(
        profile_name=str(summary.get("profile", "balanced")),
        tempo_scale=float(summary.get("tempo_scale", 1.0)),
        fps=fps_val,
        p95_lateness_us=int(lat.get("p95_us", 0)),
        p99_lateness_us=int(lat.get("p99_us", 0)),
        p95_send_duration_us=int(dur.get("p95_us", 0)),
        late_over_10ms=int(lat.get("over_10ms", 0)),
        impossible_same_key_repeats=int(sched.get("impossible_same_key_repeats", 0)),
        risky_same_key_repeats=int(sched.get("risky_same_key_repeats", 0)),
        failed_release_count=int(backend.get("panic_release_failures", 0)),
    )
