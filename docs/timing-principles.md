# The Golden Principles of Timing Profiles

This document serves as the definitive guide for understanding and configuring the timing macros in Sky Player. The parameters defined in `config.py` (`DEFAULT_TIMING_PROFILES`) are not arbitrary; they are strictly bound by the physics of the game engine's input polling and network transmission latency.

When tuning or creating new profiles, you **MUST** adhere to these five fundamental rules.

---

## 1. The Cycle Rule (The Math of Polling)
**Formula:** `Cycle = min_hold_us + repeat_release_gap_us`

*   **The Concept:** This represents the total time it takes for a key to go `DOWN`, come `UP`, and be ready to go `DOWN` again.
*   **The Rule:** The `Cycle` **MUST** be strictly greater than the duration of one game frame. Game engines (like Unity) process input queues once per frame. If the entire sequence (Down -> Up -> Down) happens faster than one frame, the engine squashes the events together, and the second note is dropped entirely.
*   **Guidelines:**
    *   Targeting **60 FPS** (16.67ms/frame) -> Cycle must be **18ms - 21ms**.
    *   Targeting **30 FPS** (33.33ms/frame) -> Cycle must be **> 35ms**. *(Note: The system's `FrameTimingPolicy` automatically scales ratios to achieve this for 30fps users).*

## 2. The Visibility Rule
**Parameter:** `min_hold_us` (Minimum Hold Time)

*   **The Concept:** When notes are scheduled very close together, the system compresses the hold duration to make room for the next note.
*   **The Rule:** Never set `min_hold_us` too low. No matter how fast you want to repeat a key, the key **must be held down long enough for the Game Engine to catch it** during its polling tick.
*   **Guidelines:**
    *   **Local Play:** **10ms - 16ms**.
    *   **Cloud/Remote Play:** **>= 20ms** (Network transmission can degrade or shorten micro-inputs, so they must be exaggerated).

## 3. The Network Coalescing Rule
**Parameter:** `repeat_release_gap_us` (The gap between releasing and re-pressing the same key)

*   **The Concept:** The period of "silence" where the key is fully released.
*   **The Rule:** Locally, this only needs to be long enough for the OS to register an `UP` event. Over a network (Parsec, Moonlight, Cloud), if events are sent too close together, the network router or protocol will coalesce (merge) them into a single packet to save bandwidth, destroying the repeat action.
*   **Guidelines:**
    *   **Local Play:** **5ms - 8ms**.
    *   **Cloud/Remote Play:** **>= 15ms** (Forces TCP/UDP to separate the `UP` and `DOWN` commands into distinct physical network packets).

## 4. The Chord Batching Rule
**Parameter:** `chord_merge_window_us` (The tolerance window to snap nearby notes into a single simultaneous chord)

*   **The Rule:**
    *   **Local Play:** Keep it **VERY SMALL (2ms - 3ms)**. Slightly misaligned MIDI notes sound more human and realistic (strumming effect).
    *   **Cloud/Remote Play:** Keep it **LARGE (4ms - 6ms+)**. The more keys you snap into a single exact microsecond, the more keys get packed into a **single network payload**. This drastically reduces network spam/jitter and ensures chords sound unified on the receiving end rather than rattling sporadically.

## 5. The Input Lead Rule
**Parameter:** `input_lead_us` (Shifting the timestamp backward to send the command early)

*   **The Concept:** Compensates for the inherent delay between the code executing and the game engine actually parsing the input.
*   **The Rule:**
    *   **Local Play (Strong PC):** **3ms - 6ms** (Compensates for OS and virtual keyboard drivers).
    *   **Cloud/Remote Play:** **12ms - 15ms** (Directly compensates for network ping/latency).

---

## Quick Reference: Built-in Profiles

| Profile | Min Hold | Release Gap | **Total Cycle** | Max Repeat Speed | Design Characteristics |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `local_precise` | 12ms | 6ms | **18ms** | ~55 notes/sec | Hugs the absolute mathematical limit of 60FPS. Extremely sharp and fast. |
| `balanced` | 14ms | 7ms | **21ms** | ~47 notes/sec | Excellent margin of error. Accommodates slight OS jitter and frame drops. |
| `dense_safe` | 10ms | 8ms | **18ms** | ~55 notes/sec | Designed for insanely dense MIDI files. Prioritizes a long release gap to clear OS buffers. |
| `remote_safe` | 20ms | 15ms | **35ms** | ~28 notes/sec | Slowed down by design. Guarantees 100% survival over laggy network streams. |
