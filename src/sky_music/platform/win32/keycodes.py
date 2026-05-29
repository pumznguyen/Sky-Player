import ctypes
from sky_music.layouts import NoteResolver, PHYSICAL_SCAN_CODES, VK_CODES
from sky_music.domain import InstrumentProfile, NoteKey

class Win32NoteResolver:
    def __init__(self, profile: InstrumentProfile):
        self.profile = profile

    def resolve_scan_code(self, note_key: str, scan_code_mode: str = "physical") -> int:
        mapped_key = self.profile.key_map.get(NoteKey(note_key))
        if not mapped_key:
            return 0
            
        if scan_code_mode == "physical" and mapped_key in PHYSICAL_SCAN_CODES:
            return PHYSICAL_SCAN_CODES[mapped_key]
            
        # Virtual Key mode fallback
        vk_code = VK_CODES.get(mapped_key)
        if vk_code is not None:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                return user32.MapVirtualKeyW(vk_code, 0)
            except (AttributeError, OSError):
                # Fallback in case of environment mismatch or test environment
                pass
        
        # Safe fallback to physical code if VK mapping fails or user32 is missing
        if mapped_key in PHYSICAL_SCAN_CODES:
            return PHYSICAL_SCAN_CODES[mapped_key]
            
        return 0
