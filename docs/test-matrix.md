# Project Test Matrix

This document provides a systematic verification matrix for the Sky music player precision playback engine, specifying automated unit tests and manual verification procedures.

---

## 🤖 1. Automated Verification Suite (`pytest`)

We maintain a suite of 24 automated tests verifying scheduler timing, parser schemas, CLI parameters, and layouts:

| Module | Test Case | Target Checked | Verification |
| :--- | :--- | :--- | :--- |
| **`tests/test_layouts.py`** | `test_layout_completeness` | Verifies the standard 15-key profile maps unique key indexes correctly. | Asserts exactly 15 unique physical QWERTY characters are mapped. |
| | `test_legacy_compatibility_keys` | Verifies prefix fallbacks (`1Key`, `2Key`) are supported seamlessly. | Asserts correct compatibility dict indices mappings. |
| **`tests/test_parser.py`** | `test_valid_song_parses` | Validates a standard JSON song parses correctly. | Asserts timestamps and key names match values. |
| | `test_unknown_key_fails` | Rejects unknown key characters immediately. | Raises `SongValidationError` on unmapped key targets. |
| | `test_missing_song_notes_fails` | Rejects song formats missing `songNotes`. | Raises `SongValidationError` on corrupt top-level schema. |
| | `test_negative_time_fails` | Rejects notes scheduled with negative durations. | Raises `SongValidationError` on timestamps < 0. |
| | `test_unordered_notes_are_sorted` | Sorts out-of-order notes chronologically. | Asserts output `Song` note objects list is stably sorted. |
| | `test_chord_notes_with_same_timestamp_preserved` | Verifies notes sharing timestamps are kept. | Asserts note lists are fully preserved for chords. |
| | `test_public_load_song_data_fails_on_unknown_keys` | Verifies loader completely fails on invalid notes. | Asserts None is returned on parsing lookup failure. |
| **`tests/test_playback.py`** | `test_dry_run_playback_execution` | Verifies playback execution tick timelines. | Asserts simulation history matches precise timing sequence. |
| **`tests/test_scheduler_current_behavior.py`** | `test_single_note_creates_down_up` | Legacy float-scheduler down/up creation. | Asserts correct legacy key down/up times in seconds. |
| | `test_chord_at_same_timestamp_coalesced` | Chord grouping logic in legacy scheduler. | Asserts grouping and scan code batching. |
| | `test_same_key_repeat_compresses_hold` | Holds compression under dense schedules. | Asserts co-compresses down holds correctly. |
| | `test_impossible_same_key_repeat_counted` | Too-fast legacy same-key repeats. | Asserts impossible repeat count diagnostics. |
| **`tests/test_scheduler_new.py`** | `test_chord_batching_and_deduplication` | Deduplicates identical scan codes in chords. | Asserts only unique keys are batched together. |
| | `test_same_key_repeat_releases_first` | Key release prioritizing for repeats. | Asserts microsecond repeat release precedes new down trigger. |
| | `test_prioritization_at_same_timestamp` | Timeline order priority sorting. | Asserts repeat-up -> down -> down-up chronological order. |
| | `test_impossible_same_key_repeat_diagnostics` | High-speed same-key repeats count. | Asserts fallback holdings apply (500us) cleanly. |
| **`tests/test_calibration.py`** | `test_timing_profile_parsing` | Timing profile parameter parsing. | Asserts policy bounds match selected profile (balanced/fast/conservative). |
| | `test_timing_overrides_parsing` | Parameter override precedence. | Asserts arguments take higher priority over profiles. |
| | `test_dry_run_simulation_flag` | Simulation mode activations checks. | Asserts globals configure correctly. |
| **`tests/test_cli.py`** | `test_cli_basic_arguments` | Basic CLI argument configurations checks. | Asserts args are assigned correctly with fallback values. |
| | `test_cli_hotkeys_defaults` | Checks default hotkey bindings. | Asserts safe defaults (F8, F9, Esc, F6). |
| | `test_cli_playback_controls_parsing` | Validates keyboard binds collision checks. | Asserts ValueErrors are thrown when hotkeys clash with note keys. |

To run the automated test suite:
```bash
uv run pytest
```

---

## 👥 2. Manual Verification Suite (Sky In-Game Checks)

To guarantee safety and timing compliance with the Windows 11 target environment, perform the following in-game manual checks:

### Test 1: Doctor Diagnostics Suite
*   **Goal**: Ensure local environment constraints are perfectly met before playing.
*   **Procedure**:
    1.  Open your terminal and run:
        ```bash
        python src/main.py --doctor
        ```
    2.  Verify the terminal output lists Admin Privilege status, Multimedia Timers setup, and Keyboard Layout completeness as **OK**.
    3.  Hold down the `Y` key physically on your keyboard and run `--doctor` again. Confirm that a preflight warnings message is printed indicating key conflict detection.

### Test 2: In-Memory Dry Run
*   **Goal**: Verify scheduler accuracy and telemetry logging capabilities without using simulated OS keystrokes.
*   **Procedure**:
    1.  Run the simulation command:
        ```bash
        python src/main.py --song 1 --dry-run --debug-csv
        ```
    2.  Confirm that simulated playback triggers instantly and displays a visual progress bar.
    3.  Open the newly created telemetry CSV file in the `logs/` directory. Confirm that it lists event timestamps in microsecond columns, and lateness logs are recorded correctly.

### Test 3: Standard Playback Test
*   **Goal**: Assert timing accuracy and chord playback in-game.
*   **Procedure**:
    1.  Launch **Sky: Children of the Light** and equip an instrument.
    2.  Run the player CLI:
        ```bash
        python src/main.py --song "Song Name"
        ```
    3.  Confirm that playback countdown ticks down.
    4.  Verify that chords trigger correctly, notes are played on time, and same-key repeats do not experience noticeable input delay.

### Test 4: Focus Pause / Window Management
*   **Goal**: Ensure active keys are immediately released upon focus loss to prevent stuck notes.
*   **Procedure**:
    1.  Start playing a dense song.
    2.  `Alt+Tab` away from the game window to an unrelated window.
    3.  Confirm that:
        *   Keystroke injection stops immediately.
        *   Held keys are released cleanly (no stuck notes in-game).
        *   The CLI progress bar indicates `[FOCUS LOST]` and pauses the timeline.
    4.  `Alt+Tab` back into the Sky window. Verify that playback resumes precisely from where it paused.

### Test 5: Hotkeys Validation Check
*   **Goal**: Verify hotkey responsiveness during dense playback sections.
*   **Procedure**:
    1.  Play a song.
    2.  Press the `F8` key (default pause hotkey). Verify that the song pauses and releases all active notes. Press `F8` again to resume.
    3.  Press the `F9` key (default skip hotkey). Verify that the current song ends cleanly and returns you to the song picker screen.
    4.  Press `Esc` (default quit hotkey). Verify that the player terminates instantly.
