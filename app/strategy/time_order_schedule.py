from app.strategy.base import DispatchStrategy
from app.strategy.min_total_time import MinTotalTimeStrategy


class TimeOrderScheduleStrategy(DispatchStrategy):
    """Merge fault queue + same-type unfinished vehicles, sort by queue number, redistribute."""

    async def dispatch(self, candidates, piles, context):
        if not candidates or not piles:
            return {}
        sorted_candidates = sorted(
            candidates,
            key=lambda c: _extract_queue_num(
                c.queue_number if hasattr(c, 'queue_number') else c.get('queue_number', '')
            )
        )
        return await MinTotalTimeStrategy().dispatch(sorted_candidates, piles, context)


def _extract_queue_num(qn: str) -> int:
    try:
        return int(qn[1:])
    except (ValueError, IndexError):
        return 0
