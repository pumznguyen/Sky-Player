# Timing Baseline Audit

This document records the exact timing behavior, constants, and logic of the legacy scheduler before refactoring.

## Timing Constants

The legacy scheduler in `src/scheduler.py` hard-codes the following timing parameters (in seconds):

*   `KEY_HOLD_SECONDS` = 0.02 (20 ms) - The default duration a key is held down.
*   `MIN_KEY_HOLD_SECONDS` = 0.012 (12 ms) - The absolute minimum duration a key must be held down to be recognized by the game engine.
*   `RELEASE_GAP_SECONDS` = 0.003 (3 ms) - The safety gap required before releasing a key when it needs to be repeated soon.
*   `REPEAT_RELEASE_GAP_SECONDS` = 0.002 (2 ms) - The safety delay between a key-up and a subsequent key-down on the same key.
*   `MIN_SCHEDULED_HOLD_SECONDS` = 0.0005 (0.5 ms) - The minimum time scheduled for extremely tight note hold intervals.

## Current Key Maps

The 15-key keyboard layout is hardcoded in `src/scheduler.py` and maps to:

```text
Y U I O P
H J K L ;
N M , . /
```

With support for legacy prefixes `1Key` and `2Key` mapping to the same characters.

## Current Playback Event Loop Logic

1.  **Event Generation**:
    *   For each note, `build_playback_events` schedules a key-down event at `down_time` (with priority 1) and a key-up event at `up_time = down_time + hold` (with priority 0).
    *   `hold` is calculated by checking the time difference to the next note on the same key:
        *   If `max_hold = next_same - down_time - RELEASE_GAP_SECONDS` is less than or equal to 0, hold is set to `MIN_SCHEDULED_HOLD_SECONDS` (0.5ms) and `enforce_min_hold` is set to `False`.
        *   If `max_hold < MIN_KEY_HOLD_SECONDS`, hold is set to `max(MIN_SCHEDULED_HOLD_SECONDS, max_hold)` and `enforce_min_hold = False`.
        *   If `max_hold` is between `MIN_KEY_HOLD_SECONDS` and `KEY_HOLD_SECONDS`, hold is compressed to `max_hold` and `enforce_min_hold = True`.
        *   Otherwise, hold is set to the default `KEY_HOLD_SECONDS` (20ms) and `enforce_min_hold = True`.
2.  **Event Sorting**:
    *   All events (both down and up) are mixed in a list and sorted using `key=lambda event: (event[0], event[1])` (by time first, then by priority). Since key-down events have priority 1 and key-up events have priority 0, key-ups will execute BEFORE key-downs if they share the exact same timestamp.
3.  **Coalescing**:
    *   Events sharing the same time, priority, and `is_key_up` status are grouped so their scan codes are dispatched as a single batch (enabling chord play).
4.  **Playback Loop in `play_music` (`src/main.py`)**:
    *   Iterates through sorted, coalesced events.
    *   If the current time has not been reached, sleeps via `sleep_for_playback` (using hybrid polling and thread sleeps).
    *   For key-up events:
        *   If `enforce_min_hold` is True, it calculates the earliest release time using `active_down_started_at.get(scan_code) + MIN_KEY_HOLD_SECONDS`.
        *   If this minimum hold has not been met, it calls `wait_seconds(delay)` **blocking the main playback thread**. This sleep delays all subsequent key-down events scheduled during this interval!
    *   For key-down events:
        *   If a key is already down, it forces a repeat release, sends a key-up, removes it from active keys, and blocks for `REPEAT_RELEASE_GAP_SECONDS` (2ms) before finally performing the key-down. This causes significant latency.
