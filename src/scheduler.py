import ctypes
from inputs import user32

KEY_HOLD_SECONDS = 0.02
MIN_KEY_HOLD_SECONDS = 0.012
RELEASE_GAP_SECONDS = 0.003
REPEAT_RELEASE_GAP_SECONDS = 0.002
MIN_SCHEDULED_HOLD_SECONDS = 0.0005

VK_CODES = {
    'y': 0x59,
    'u': 0x55,
    'i': 0x49,
    'o': 0x4F,
    'p': 0x50,
    'h': 0x48,
    'j': 0x4A,
    'k': 0x4B,
    'l': 0x4C,
    ';': 0xBA,
    'n': 0x4E,
    'm': 0x4D,
    ',': 0xBC,
    '.': 0xBE,
    '/': 0xBF,
}

PHYSICAL_SCAN_CODES = {
    'y': 0x15,
    'u': 0x16,
    'i': 0x17,
    'o': 0x18,
    'p': 0x19,
    'h': 0x23,
    'j': 0x24,
    'k': 0x25,
    'l': 0x26,
    ';': 0x27,
    'n': 0x31,
    'm': 0x32,
    ',': 0x33,
    '.': 0x34,
    '/': 0x35,
}

key_maps = {
    'Key0': 'y', 'Key1': 'u', 'Key2': 'i', 'Key3': 'o', 'Key4': 'p',
    'Key5': 'h', 'Key6': 'j', 'Key7': 'k', 'Key8': 'l', 'Key9': ';',
    'Key10': 'n', 'Key11': 'm', 'Key12': ',', 'Key13': '.', 'Key14': '/',
    '1Key0': 'y', '1Key1': 'u', '1Key2': 'i', '1Key3': 'o', '1Key4': 'p',
    '1Key5': 'h', '1Key6': 'j', '1Key7': 'k', '1Key8': 'l', '1Key9': ';',
    '1Key10': 'n', '1Key11': 'm', '1Key12': ',', '1Key13': '.', '1Key14': '/',
    '2Key0': 'y', '2Key1': 'u', '2Key2': 'i', '2Key3': 'o', '2Key4': 'p',
    '2Key5': 'h', '2Key6': 'j', '2Key7': 'k', '2Key8': 'l', '2Key9': ';',
    '2Key10': 'n', '2Key11': 'm', '2Key12': ',', '2Key13': '.', '2Key14': '/',
}

NOTE_SCAN_CODES = {}

def build_note_scan_codes(note_maps, scan_code_mode="physical"):
    note_scan_codes = {}
    for note_key, mapped_key in note_maps.items():
        scan_code = 0
        if scan_code_mode == "physical" and mapped_key in PHYSICAL_SCAN_CODES:
            scan_code = PHYSICAL_SCAN_CODES[mapped_key]
        else:
            vk_code = VK_CODES.get(mapped_key)
            if vk_code is not None:
                scan_code = user32.MapVirtualKeyW(vk_code, 0)
        if scan_code == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        note_scan_codes[note_key] = scan_code
    return note_scan_codes

def coalesce_events(events):
    grouped = {}
    for t, priority, scan_codes, is_key_up, enforce_min_hold in events:
        key = (t, priority, is_key_up, enforce_min_hold)
        if key not in grouped:
            grouped[key] = []
        grouped[key].extend(scan_codes)

    coalesced = []
    for (t, priority, is_key_up, enforce_min_hold), sc_list in grouped.items():
        unique_sc = tuple(dict.fromkeys(sc_list))
        coalesced.append((t, priority, unique_sc, is_key_up, enforce_min_hold))

    coalesced.sort(key=lambda e: (e[0], e[1]))
    return tuple(coalesced)

def build_playback_events(scan_code_batches):
    down_events = []
    up_events = []
    compressed_holds = 0
    impossible_same_key_repeats = 0

    # Flatten note events
    flat = []
    for time_ms, scan_codes in scan_code_batches:
        t = time_ms / 1000
        for sc in tuple(dict.fromkeys(scan_codes)):
            flat.append((t, sc))

    # Precompute next same-key time
    next_same_key_time = {}
    last_seen_by_key = {}
    for index in range(len(flat) - 1, -1, -1):
        t, sc = flat[index]
        next_same_key_time[index] = last_seen_by_key.get(sc)
        last_seen_by_key[sc] = t

    for index, (down_time, sc) in enumerate(flat):
        next_same = next_same_key_time[index]
        if next_same is not None:
            max_hold = next_same - down_time - RELEASE_GAP_SECONDS
            if max_hold <= 0:
                impossible_same_key_repeats += 1
                compressed_holds += 1
                enforce_min_hold = False
                hold = MIN_SCHEDULED_HOLD_SECONDS
            elif max_hold < MIN_KEY_HOLD_SECONDS:
                impossible_same_key_repeats += 1
                compressed_holds += 1
                enforce_min_hold = False
                hold = max(MIN_SCHEDULED_HOLD_SECONDS, max_hold)
            elif KEY_HOLD_SECONDS > max_hold:
                compressed_holds += 1
                enforce_min_hold = True
                hold = max_hold
            else:
                hold = KEY_HOLD_SECONDS
                enforce_min_hold = True
        else:
            hold = KEY_HOLD_SECONDS
            enforce_min_hold = True

        up_time = down_time + hold
        down_events.append((down_time, 1, (sc,), False, True))
        up_events.append((up_time, 0, (sc,), True, enforce_min_hold))

    events = down_events + up_events
    events.sort(key=lambda event: (event[0], event[1]))

    return {
        "events": coalesce_events(events),
        "compressed_holds": compressed_holds,
        "impossible_same_key_repeats": impossible_same_key_repeats,
    }
