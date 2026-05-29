from dataclasses import dataclass
from typing import Literal
from sky_music.domain import Song, InstrumentProfile, ScanCode
from sky_music.layouts import SKY_15_KEY_PROFILE, PHYSICAL_SCAN_CODES, VK_CODES
import ctypes

@dataclass(frozen=True, slots=True)
class TimingPolicy:
    hold_us: int = 20_000                  # 20ms default hold
    min_hold_us: int = 12_000              # 12ms absolute min hold
    release_gap_us: int = 3_000            # 3ms safety release gap
    repeat_release_gap_us: int = 2_000     # 2ms gap before same-key repeats
    min_scheduled_hold_us: int = 500       # 0.5ms fallback hold

@dataclass(frozen=True, slots=True)
class KeyAction:
    at_us: int
    scan_codes: tuple[ScanCode, ...]
    kind: Literal["down", "up"]
    reason: Literal["note", "release", "repeat_release", "final_release"]

def get_note_scan_code(note_key: str, profile: InstrumentProfile, scan_code_mode: str = "physical") -> int:
    """Helper to map a note key to its Windows scan code based on the profile layout."""
    mapped_key = profile.key_map.get(note_key)
    if not mapped_key:
        return 0
        
    if scan_code_mode == "physical" and mapped_key in PHYSICAL_SCAN_CODES:
        return PHYSICAL_SCAN_CODES[mapped_key]
        
    # Virtual Key mode fallback
    vk_code = VK_CODES.get(mapped_key)
    if vk_code is not None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        return user32.MapVirtualKeyW(vk_code, 0)
    return 0

def build_key_actions(
    song: Song,
    profile: InstrumentProfile = SKY_15_KEY_PROFILE,
    policy: TimingPolicy = TimingPolicy(),
    scan_code_mode: str = "physical"
) -> dict:
    """
    Builds a microsecond-accurate event timeline from a domain Song.
    Returns a dictionary containing:
      - 'actions': tuple of sorted KeyAction objects
      - 'compressed_holds': count of note holds compressed due to dense scheduling
      - 'impossible_same_key_repeats': count of repeats scheduled too fast to meet min-hold
      - 'max_polyphony': maximum number of notes pressed simultaneously
      - 'note_count': total number of notes scheduled
    """
    compressed_holds = 0
    impossible_same_key_repeats = 0
    note_count = len(song.notes)
    
    # 1. Flatten all notes into a list of (time_us, scan_code)
    flat_notes = []
    for idx, note in enumerate(song.notes):
        time_us = note.time_ms * 1000
        sc = get_note_scan_code(note.key, profile, scan_code_mode)
        if sc <= 0:
            raise ValueError(
                f"Cannot map note key {note.key!r} to a scan code "
                f"(scan_code_mode={scan_code_mode!r}, profile={profile.name!r})"
            )
        flat_notes.append((time_us, sc, idx))
            
    # Sort flat_notes chronologically
    flat_notes.sort(key=lambda n: n[0])
    
    # 2. Pre-calculate the next occurrence time of the same physical key
    next_same_key_time = {}
    last_seen_by_key = {}
    for idx in range(len(flat_notes) - 1, -1, -1):
        time_us, sc, note_idx = flat_notes[idx]
        next_same_key_time[note_idx] = last_seen_by_key.get(sc)
        last_seen_by_key[sc] = time_us
        
    raw_events = [] # list of dicts: {"at_us": int, "sc": int, "kind": "down"|"up", "reason": str}
    
    # 3. Schedule down/up bounds for each individual note
    for time_us, sc, note_idx in flat_notes:
        next_same = next_same_key_time[note_idx]
        
        # Calculate maximum possible hold duration for this key
        if next_same is not None:
            max_hold = next_same - time_us - policy.repeat_release_gap_us
            
            if max_hold <= 0:
                impossible_same_key_repeats += 1
                compressed_holds += 1
                hold = policy.min_scheduled_hold_us
                reason_up = "repeat_release"
            elif max_hold < policy.min_hold_us:
                impossible_same_key_repeats += 1
                compressed_holds += 1
                hold = max(policy.min_scheduled_hold_us, max_hold)
                reason_up = "repeat_release"
            elif max_hold < policy.hold_us:
                compressed_holds += 1
                hold = max_hold
                reason_up = "repeat_release"
            else:
                hold = policy.hold_us
                reason_up = "release"
        else:
            hold = policy.hold_us
            reason_up = "final_release"
            
        down_us = time_us
        up_us = time_us + hold
        
        raw_events.append({"at_us": down_us, "sc": sc, "kind": "down", "reason": "note"})
        raw_events.append({"at_us": up_us, "sc": sc, "kind": "up", "reason": reason_up})
        
    # 3.5 Delay normal releases that coincide with note down onsets to safety gap
    down_timestamps = {ev["at_us"] for ev in raw_events if ev["kind"] == "down"}
    for ev in raw_events:
        if ev["kind"] == "up" and ev["reason"] in ("release", "final_release"):
            if ev["at_us"] in down_timestamps:
                ev["at_us"] += policy.release_gap_us
        
    # 4. Group (coalesce) events at the exact same timestamp + kind
    # To prioritize key-downs and prevent blocking, we group them cleanly.
    grouped = {} # key: (at_us, kind, reason) -> list of scan codes
    for ev in raw_events:
        g_key = (ev["at_us"], ev["kind"], ev["reason"])
        if g_key not in grouped:
            grouped[g_key] = []
        grouped[g_key].append(ev["sc"])
        
    # Build a raw list of grouped KeyActions
    key_actions_list = []
    for (at_us, kind, reason), scs in grouped.items():
        # Ensure unique scan codes in a batch (e.g. chord batching)
        unique_scs = tuple(dict.fromkeys(scs))
        key_actions_list.append(KeyAction(
            at_us=at_us,
            scan_codes=unique_scs,
            kind=kind,
            reason=reason
        ))
        
    # 5. Sort the final timeline with strict microsecond accuracy & kind prioritization
    # Priority at the exact same microsecond:
    # 1st: Same-key repeats key-up ("repeat_release") - MUST release before pressing down again
    # 2nd: Key-down ("down") - Note onset
    # 3rd: Normal key-up ("release") - Unrelated releases, can happen slightly after down
    # 4th: Final releases ("final_release") - Safe to do last
    def action_priority(action: KeyAction) -> int:
        if action.kind == "up":
            if action.reason == "repeat_release":
                return 0 # Release repeat keys first!
            elif action.reason == "release":
                return 2 # Safe release after down
            else:
                return 3 # Final release last
        else:
            return 1 # Down note onset has priority over standard releases
            
    key_actions_list.sort(key=lambda a: (a.at_us, action_priority(a)))
    
    # 6. Calculate max polyphony (simultaneous active down keys)
    active_keys = set()
    max_polyphony = 0
    for action in key_actions_list:
        if action.kind == "down":
            active_keys.update(action.scan_codes)
            max_polyphony = max(max_polyphony, len(active_keys))
        else:
            active_keys.difference_update(action.scan_codes)
            
    return {
        "actions": tuple(key_actions_list),
        "compressed_holds": compressed_holds,
        "impossible_same_key_repeats": impossible_same_key_repeats,
        "max_polyphony": max_polyphony,
        "note_count": note_count
    }
