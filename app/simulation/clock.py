from datetime import datetime, timedelta


class VirtualClock:
    def __init__(self, start_time: datetime | None = None, tick_minutes: int = 15):
        self._current = start_time or datetime.now()
        self.tick_minutes = tick_minutes

    @property
    def now(self) -> datetime:
        return self._current

    def tick(self) -> datetime:
        self._current += timedelta(minutes=self.tick_minutes)
        return self._current

    def set(self, dt: datetime) -> None:
        self._current = dt

    def to_dict(self) -> dict:
        return {
            "current_time": self._current.isoformat(),
            "tick_minutes": self.tick_minutes,
        }


clock = VirtualClock()
