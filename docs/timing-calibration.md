# Timing Calibration Guide

This document describes how to calibrate the Sky music playback helper to achieve the highest timing accuracy on your Windows machine using the new microsecond-accurate engine.

## Predefined Timing Profiles

Three profiles are available out-of-the-box depending on your PC's hardware speed, overlay overheads, and background resource usage:

1.  **`fast`**: Designed for high-end systems with low latency display buffers.
    *   `hold_ms` = 16
    *   `min_hold_ms` = 8
    *   `release_gap_ms` = 2
2.  **`balanced`** (Default): Optimal for most computers.
    *   `hold_ms` = 24
    *   `min_hold_ms` = 12
    *   `release_gap_ms` = 3
3.  **`conservative`**: High compatibility profile for low-spec rigs or systems with severe background CPU load.
    *   `hold_ms` = 34
    *   `min_hold_ms` = 16
    *   `release_gap_ms` = 5

---

## Measuring Playback Timing Deviation (Telemetry Logs)

The precision playback engine allows you to record exact timing data for analysis.

To generate a CSV telemetry report:
```bash
python src/main.py --song "Song Name" --debug-csv
```
This writes a CSV file to `logs/playback_telemetry_YYYYMMDD_HHMMSS.csv` containing:
```csv
song,event_index,kind,scheduled_us,actual_us,lateness_us,scan_codes,reason
```

### Analyzing `lateness_us` (Microsecond Lateness)
*   `lateness_us = actual_us - scheduled_us`
*   If `lateness_us` is **less than 2000** (2ms) consistently: Your system is performing outstandingly.
*   If `lateness_us` is **frequently over 5000** (5ms): Your timing is moderately degraded. 
*   If `lateness_us` is **frequently over 10000** (10ms): Keystrokes are experiencing substantial stuttering, which can degrade musical playback.

---

## How to Calibrate Your Rigs

If telemetry reports indicate timing lateness, consider adjusting timing constants manually using command-line overrides:

```bash
python src/main.py --song "Song Name" --hold-ms 20 --min-hold-ms 10 --release-gap-ms 4 --debug-csv
```

### Quick Diagnostic: Dry-Run Mode
Before playing the song physically in-game, you can perform a high-speed timing simulation in memory to check timing logic correctness without window focus constraints:
```bash
python src/main.py --song 1 --dry-run --debug-csv
```
This simulation generates a CSV report instantly, confirming that the microsecond scheduler handles repeats, chord-batches, and polyphony correctly under the hood.
