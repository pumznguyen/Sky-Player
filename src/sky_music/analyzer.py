from dataclasses import dataclass
from typing import Literal
from sky_music.scheduler_types import ScheduleResult

@dataclass(frozen=True, slots=True)
class DenseCluster:
    start_us: int
    end_us: int
    note_count: int

@dataclass(frozen=True, slots=True)
class ScheduleRiskReport:
    severity: Literal["low", "medium", "high"]
    impossible_repeats: int
    compressed_holds: int
    max_polyphony: int
    min_any_note_gap_us: int | None
    min_same_key_gap_us: int | None
    dense_clusters: tuple[DenseCluster, ...]
    recommendations: tuple[str, ...]

def analyze_schedule(res: ScheduleResult) -> ScheduleRiskReport:
    """Analyze a ScheduleResult to detect potential timing conflicts, density risks, and suggest overrides."""
    down_events = sorted([action for action in res.actions if action.kind == "down"], key=lambda a: a.at_us)
    n = len(down_events)
    
    # 1. Sliding Window O(n) scan to identify dense clusters (> 6 notes within any 100ms)
    dense_clusters_list = []
    left = 0
    for right in range(n):
        while down_events[right].at_us - down_events[left].at_us > 100_000:
            left += 1
            
        note_count = right - left + 1
        if note_count > 6:
            start_us = down_events[left].at_us
            end_us = down_events[right].at_us
            
            # Coalesce/merge overlapping dense clusters to avoid duplicate warnings
            if dense_clusters_list and start_us <= dense_clusters_list[-1].end_us + 50_000:
                prev = dense_clusters_list[-1]
                dense_clusters_list[-1] = DenseCluster(
                    start_us=prev.start_us,
                    end_us=end_us,
                    note_count=max(prev.note_count, note_count)
                )
            else:
                dense_clusters_list.append(DenseCluster(
                    start_us=start_us,
                    end_us=end_us,
                    note_count=note_count
                ))
                
    # 2. Compute minimum gap between ANY two notes
    min_any_note_gap_us = None
    if n > 1:
        min_any_note_gap_us = min(down_events[i].at_us - down_events[i-1].at_us for i in range(1, n))
        
    # 3. Compute minimum gap between repeats of the SAME physical key
    min_same_key_gap_us = None
    key_last_down = {}
    same_key_gaps = []
    
    for action in res.actions:
        if action.kind == "down":
            for sc in action.scan_codes:
                if sc in key_last_down:
                    same_key_gaps.append(action.at_us - key_last_down[sc])
                key_last_down[sc] = action.at_us
                
    if same_key_gaps:
        min_same_key_gap_us = min(same_key_gaps)
        
    # 4. Evaluate risk severity
    severity: Literal["low", "medium", "high"] = "low"
    recommendations = []
    
    if res.impossible_same_key_repeats > 0:
        severity = "high"
        recommendations.append(
            f"Found {res.impossible_same_key_repeats} impossible same-key repeats. "
            "Recommending --tempo-scale 0.8 or switching to --timing-profile remote-safe to prevent clipped keystrokes."
        )
        
    dense_count = len(dense_clusters_list)
    if dense_count > 5:
        if severity != "high":
            severity = "high" if dense_count > 15 else "medium"
        recommendations.append(
            f"Detected {dense_count} distinct dense cluster(s) (more than 6 notes in 100ms). "
            "Recommending --timing-profile dense-safe to optimize chord release overlap."
        )
        
    if res.compressed_holds > 5:
        if severity == "low":
            severity = "medium"
        recommendations.append(
            f"Compressed {res.compressed_holds} note holds due to dense scheduling. "
            "Using --timing-profile dense-safe will improve local note registration."
        )
        
    if res.max_polyphony > 8:
        if severity == "low":
            severity = "medium"
        recommendations.append(
            f"High polyphony detected (max {res.max_polyphony} simultaneous down keys). "
            "Verify your physical keyboard supports multi-key rollover (anti-ghosting)."
        )
        
    if not recommendations:
        recommendations.append("Timeline is highly optimal! Standard balanced playback is recommended.")
        
    return ScheduleRiskReport(
        severity=severity,
        impossible_repeats=res.impossible_same_key_repeats,
        compressed_holds=res.compressed_holds,
        max_polyphony=res.max_polyphony,
        min_any_note_gap_us=min_any_note_gap_us,
        min_same_key_gap_us=min_same_key_gap_us,
        dense_clusters=tuple(dense_clusters_list),
        recommendations=tuple(recommendations)
    )
