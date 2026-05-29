from dataclasses import dataclass
from typing import Protocol
import time

class Clock(Protocol):
    def now_us(self) -> int:
        """Returns the current monotonic system or simulation time in microseconds."""
        ...

class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None:
        """Suspends execution for a specified duration in seconds."""
        ...

class PerfCounterClock:
    def now_us(self) -> int:
        return time.perf_counter_ns() // 1000

class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

@dataclass(frozen=True, slots=True)
class SleepPolicy:
    spin_threshold_s: float = 0.05
    poll_s: float = 0.025
    min_sleep_s: float = 0.001
