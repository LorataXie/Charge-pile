from app.strategy.base import DispatchStrategy


class PriorityScheduleStrategy(DispatchStrategy):
    """Fault vehicles get absolute priority over waiting area vehicles."""

    async def dispatch(self, candidates, piles, context):
        if not candidates or not piles:
            return {}

        assignments = {}
        for candidate in candidates:
            mode = candidate.mode if hasattr(candidate, 'mode') else candidate.get('mode')
            order_id = candidate.id if hasattr(candidate, 'id') else candidate.get('id')
            requested_kwh = candidate.requested_kwh if hasattr(candidate, 'requested_kwh') else candidate.get('requested_kwh')

            same_mode_piles = [p for p in piles if _p_mode(p) == mode]
            available_piles = [
                p for p in same_mode_piles
                if len(context.get('pile_queues', {}).get(_p_id(p), [])) < context.get('queue_len', 3)
            ]
            if not available_piles:
                continue

            best_pile = None
            min_time = float('inf')
            for pile in available_piles:
                power_rate = pile.power_rate if hasattr(pile, 'power_rate') else pile.get('power_rate')
                queue_entries = context.get('pile_queues', {}).get(_p_id(pile), [])
                waiting_time = sum(e.get('requested_kwh', 0) / power_rate for e in queue_entries)
                own_time = requested_kwh / power_rate
                total = waiting_time + own_time
                if total < min_time:
                    min_time = total
                    best_pile = pile

            if best_pile is not None:
                assignments[order_id] = _p_id(best_pile)

        return assignments


def _p_id(pile):
    return pile.id if hasattr(pile, 'id') else pile.get('id')


def _p_mode(pile):
    return pile.mode if hasattr(pile, 'mode') else pile.get('mode')
