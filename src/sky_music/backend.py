from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class BackendHealth:
    active_count: int
    possibly_active_count: int
    failed_release_count: int
    last_error: str | None

class InputBackend(Protocol):
    """Protocol interface defining operations for keyboard note key injections."""
    def key_down(self, scan_codes: tuple[int, ...]) -> None:
        """Presses down a set of keyboard keys simultaneously."""
        ...
        
    def key_up(self, scan_codes: tuple[int, ...]) -> None:
        """Releases a set of keyboard keys simultaneously."""
        ...
        
    def release_all(self) -> None:
        """Safely releases all currently held keys."""
        ...

    def get_health(self) -> BackendHealth:
        """Returns the current health telemetry of the input backend."""
        ...

class WinSendInputBackend:
    """Windows-specific SendInput backend wrapper with safety tracking and panic release."""
    def __init__(self):
        # Dynamically import inputs to avoid cross-import problems
        import inputs
        self.inputs_module = inputs
        self.active_keys = set()
        self.possibly_active_keys = set()
        self.failed_release_keys = set()
        self.last_error: str | None = None
        
    def get_health(self) -> BackendHealth:
        return BackendHealth(
            active_count=len(self.active_keys),
            possibly_active_count=len(self.possibly_active_keys),
            failed_release_count=len(self.failed_release_keys),
            last_error=self.last_error
        )
        
    def key_down(self, scan_codes: tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        
        # Add targeted keys to possibly_active_keys before injection
        self.possibly_active_keys.update(unique_scan_codes)
        
        try:
            self.inputs_module.send_scan_code_batch(unique_scan_codes, key_up=False)
            # Acknowledged: move to active_keys and clear from possibly_active_keys
            self.active_keys.update(unique_scan_codes)
            self.possibly_active_keys.difference_update(unique_scan_codes)
        except Exception as e:
            self.last_error = f"key_down error: {e}"
            # Best-effort emergency cleanup in case SendInput partially succeeded.
            try:
                self.inputs_module.send_scan_code_batch(unique_scan_codes, key_up=True)
                self.possibly_active_keys.difference_update(unique_scan_codes)
            except Exception as ex:
                # If cleanup fails, we keep them in possibly_active_keys to track potential sticking
                self.last_error = f"key_down emergency cleanup failed: {ex}"
            raise
        
    def key_up(self, scan_codes: tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        to_release = tuple(sc for sc in unique_scan_codes if sc in self.active_keys or sc in self.possibly_active_keys)
        if to_release:
            try:
                self.inputs_module.send_scan_code_batch(to_release, key_up=True)
                self.active_keys.difference_update(to_release)
                self.possibly_active_keys.difference_update(to_release)
                self.failed_release_keys.difference_update(to_release)
            except Exception as e:
                # Key up failed: transition keys to failed_release_keys
                self.failed_release_keys.update(to_release)
                self.last_error = f"key_up error: {e}"
                raise
            
    def release_all(self) -> None:
        import time
        # Form union of all tracked potentially active keys
        to_release = self.active_keys | self.possibly_active_keys | self.failed_release_keys
        if not to_release:
            return
            
        release_tuple = tuple(to_release)
        
        # Attempt 3-pass release sequence spaced 15ms apart
        for pass_idx in range(3):
            try:
                self.inputs_module.send_scan_code_batch(release_tuple, key_up=True)
                # Successful release: clear all tracking sets
                self.active_keys.clear()
                self.possibly_active_keys.clear()
                self.failed_release_keys.clear()
                return
            except Exception as e:
                self.last_error = f"release_all pass {pass_idx} error: {e}"
                if pass_idx == 2:
                    self.failed_release_keys.update(to_release)
                    try:
                        self.inputs_module.debug_log(
                            f"[backend] Panic release failed after 3 passes: {e}. "
                            f"Remaining stuck keys: {self.failed_release_keys}"
                        )
                    except Exception:
                        pass
                else:
                    time.sleep(0.015)

class DryRunBackend:
    """Mock backend useful for timing analysis, safety state validation, and testing."""
    def __init__(self):
        self.history = [] # Records tuples of (action_type, scan_codes)
        self.active_keys = set()
        self.possibly_active_keys = set()
        self.failed_release_keys = set()
        
    def get_health(self) -> BackendHealth:
        return BackendHealth(
            active_count=len(self.active_keys),
            possibly_active_count=len(self.possibly_active_keys),
            failed_release_count=len(self.failed_release_keys),
            last_error=None
        )
        
    def key_down(self, scan_codes: tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        self.possibly_active_keys.update(unique_scan_codes)
        
        # Simulate success for dry run
        self.active_keys.update(unique_scan_codes)
        self.possibly_active_keys.difference_update(unique_scan_codes)
        self.history.append(("down", tuple(sorted(unique_scan_codes))))
        
    def key_up(self, scan_codes: tuple[int, ...]) -> None:
        if not scan_codes:
            return
        unique_scan_codes = tuple(dict.fromkeys(scan_codes))
        to_release = tuple(sc for sc in unique_scan_codes if sc in self.active_keys or sc in self.possibly_active_keys)
        if to_release:
            self.active_keys.difference_update(to_release)
            self.possibly_active_keys.difference_update(to_release)
            self.failed_release_keys.difference_update(to_release)
            self.history.append(("up", tuple(sorted(to_release))))
            
    def release_all(self) -> None:
        to_release = self.active_keys | self.possibly_active_keys | self.failed_release_keys
        if to_release:
            self.history.append(("up", tuple(sorted(to_release))))
            self.active_keys.clear()
            self.possibly_active_keys.clear()
            self.failed_release_keys.clear()
