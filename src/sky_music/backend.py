from typing import Protocol, Tuple
import sys

class InputBackend(Protocol):
    """Protocol interface defining operations for keyboard note key injections."""
    def key_down(self, scan_codes: Tuple[int, ...]) -> None:
        """Presses down a set of keyboard keys simultaneously."""
        ...
        
    def key_up(self, scan_codes: Tuple[int, ...]) -> None:
        """Releases a set of keyboard keys simultaneously."""
        ...
        
    def release_all(self) -> None:
        """Safely releases all currently held keys."""
        ...

class WinSendInputBackend:
    """Windows-specific SendInput backend wrapper."""
    def __init__(self):
        # Dynamically import inputs to avoid cross-import problems
        import inputs
        self.inputs_module = inputs
        self.active_keys = set()
        
    def key_down(self, scan_codes: Tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        try:
            self.inputs_module.send_scan_code_batch(unique_scan_codes, key_up=False)
        except Exception:
            # Best-effort emergency cleanup in case SendInput partially succeeded.
            try:
                self.inputs_module.send_scan_code_batch(unique_scan_codes, key_up=True)
            except Exception:
                pass
            raise
        self.active_keys.update(unique_scan_codes)
        
    def key_up(self, scan_codes: Tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        to_release = tuple(sc for sc in unique_scan_codes if sc in self.active_keys)
        if to_release:
            self.inputs_module.send_scan_code_batch(to_release, key_up=True)
            self.active_keys.difference_update(to_release)
            
    def release_all(self) -> None:
        if self.active_keys:
            self.inputs_module.send_scan_code_batch(tuple(self.active_keys), key_up=True)
            self.active_keys.clear()

class DryRunBackend:
    """Mock backend useful for timing analysis and non-Windows unit testing."""
    def __init__(self):
        self.history = [] # Records tuples of (action_type, scan_codes)
        self.active_keys = set()
        
    def key_down(self, scan_codes: Tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        self.active_keys.update(unique_scan_codes)
        self.history.append(("down", tuple(sorted(unique_scan_codes))))
        
    def key_up(self, scan_codes: Tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        to_release = tuple(sc for sc in unique_scan_codes if sc in self.active_keys)
        if to_release:
            self.active_keys.difference_update(to_release)
            self.history.append(("up", tuple(sorted(to_release))))
            
    def release_all(self) -> None:
        if self.active_keys:
            self.history.append(("up", tuple(sorted(self.active_keys))))
            self.active_keys.clear()
