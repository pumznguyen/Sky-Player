from dataclasses import dataclass
from typing import Literal, NewType

Microseconds = NewType("Microseconds", int)
ScanCode = NewType("ScanCode", int)

ActionKind = Literal["down", "up"]
ActionReason = Literal["note", "release", "repeat_release", "final_release"]

@dataclass(frozen=True, slots=True)
class KeyAction:
    at_us: Microseconds
    scan_codes: tuple[ScanCode, ...]
    kind: ActionKind
    reason: ActionReason

@dataclass(frozen=True, slots=True)
class TimingPolicy:
    hold_us: Microseconds = Microseconds(20_000)
    min_hold_us: Microseconds = Microseconds(12_000)
    release_gap_us: Microseconds = Microseconds(3_000)
    repeat_release_gap_us: Microseconds = Microseconds(2_000)
    min_scheduled_hold_us: Microseconds = Microseconds(500)

    @classmethod
    def local_precise(cls) -> "TimingPolicy":
        return cls(
            hold_us=Microseconds(20_000),
            min_hold_us=Microseconds(12_000),
            release_gap_us=Microseconds(3_000),
            repeat_release_gap_us=Microseconds(2_000),
            min_scheduled_hold_us=Microseconds(500)
        )

    @classmethod
    def remote_safe(cls) -> "TimingPolicy":
        return cls(
            hold_us=Microseconds(30_000),
            min_hold_us=Microseconds(15_000),
            release_gap_us=Microseconds(10_000),
            repeat_release_gap_us=Microseconds(8_000),
            min_scheduled_hold_us=Microseconds(500)
        )

    @classmethod
    def dense_safe(cls) -> "TimingPolicy":
        return cls(
            hold_us=Microseconds(24_000),
            min_hold_us=Microseconds(12_000),
            release_gap_us=Microseconds(5_000),
            repeat_release_gap_us=Microseconds(6_000),
            min_scheduled_hold_us=Microseconds(500)
        )

    @classmethod
    def from_profile_name(cls, name: str) -> "TimingPolicy":
        name_clean = name.lower().replace("-", "_")
        if name_clean == "local_precise":
            return cls.local_precise()
        elif name_clean == "remote_safe":
            return cls.remote_safe()
        elif name_clean == "dense_safe":
            return cls.dense_safe()
        else:
            return cls()

@dataclass(frozen=True, slots=True)
class ScheduleResult:
    actions: tuple[KeyAction, ...]
    compressed_holds: int
    impossible_same_key_repeats: int
    max_polyphony: int
    note_count: int
    duration_us: Microseconds
    warnings: tuple[str, ...]
