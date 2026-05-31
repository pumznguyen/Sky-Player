# Timing Calibration Guide

This document describes how to calibrate the Sky music playback helper to achieve the highest timing accuracy on your Windows machine using the new microsecond-accurate engine.

## Predefined Timing Profiles

Four profiles are available out-of-the-box. FPS-aware scaling is applied after the base profile is selected, so low-FPS playback can increase hold and gap values automatically.

1.  **`local-precise`**: Lowest-latency local playback for stable PCs.
    *   `hold_ms` = 20
    *   `min_hold_ms` = 12
    *   `release_gap_ms` = 3
2.  **`balanced`** (Default): General-purpose profile for most systems.
    *   `hold_ms` = 24
    *   `min_hold_ms` = 12
    *   `release_gap_ms` = 3
3.  **`remote-safe`**: Longer, clearer holds for remote listeners or low frame rates.
    *   `hold_ms` = 30
    *   `min_hold_ms` = 15
    *   `release_gap_ms` = 10
4.  **`dense-safe`**: Safer for dense chords and same-key repeats.
    *   `hold_ms` = 24
    *   `min_hold_ms` = 12
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
song,event_index,kind,scheduled_us,actual_us,lateness_us,send_duration_us,scan_codes,reason
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

Or use the telemetry calibration flow:

```bash
# 1. Record a real playback run.
python src/main.py --song "Song Name" --debug-csv

# 2. Print recommendations from the latest telemetry summary.
python src/main.py --auto-calibrate

# 3. Apply recommendations for this process only.
python src/main.py --apply-calibration

# 4. Persist recommended profile, tempo, FPS, and input lead to config.json.
python src/main.py --save-calibration

# Optional: calibrate from a specific summary, CSV, or logs directory.
python src/main.py --save-calibration --calibration-summary logs/run.summary.json
```

`--apply-calibration` does not modify `config.json`. `--save-calibration` persists defaults, but it intentionally does not store already frame-scaled hold values; those are recomputed from the saved profile and FPS at startup.

The interactive picker exposes the same saved-calibration flow from the `C` key. It shows the latest telemetry recommendation first; pressing Enter from that view saves it.

### Quick Diagnostic: Dry-Run Mode
Before playing the song physically in-game, you can perform a high-speed timing simulation in memory to check timing logic correctness without window focus constraints:
```bash
python src/main.py --song 1 --dry-run --debug-csv
```
This simulation generates a CSV report instantly, confirming that the microsecond scheduler handles repeats, chord-batches, and polyphony correctly under the hood.
