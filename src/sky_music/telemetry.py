import csv
from pathlib import Path
import time
from typing import Tuple

class TelemetryLogger:
    """Records precise microsecond timing metrics into clean CSV files for calibration."""
    def __init__(self, song_name: str, enabled: bool = False):
        self.song_name = song_name
        self.enabled = enabled
        self.records = []
        self.log_filepath = None
        
        if self.enabled:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            self.log_filepath = logs_dir / f"playback_telemetry_{timestamp}.csv"
            
    def record(
        self,
        event_index: int,
        kind: str,
        scheduled_us: int,
        actual_us: int,
        lateness_us: int,
        send_duration_us: int,
        scan_codes: Tuple[int, ...],
        reason: str
    ) -> None:
        if not self.enabled:
            return
            
        scan_codes_str = ";".join(str(sc) for sc in scan_codes)
        self.records.append({
            "song": self.song_name,
            "event_index": event_index,
            "kind": kind,
            "scheduled_us": scheduled_us,
            "actual_us": actual_us,
            "lateness_us": lateness_us,
            "send_duration_us": send_duration_us,
            "scan_codes": scan_codes_str,
            "reason": reason
        })
        
    def save(self) -> None:
        if not self.enabled or not self.log_filepath or not self.records:
            return
            
        try:
            fields = ["song", "event_index", "kind", "scheduled_us", "actual_us", "lateness_us", "send_duration_us", "scan_codes", "reason"]
            with self.log_filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(self.records)
        except Exception as e:
            # Silently swallow telemetry logging errors to avoid disrupting playback
            pass
