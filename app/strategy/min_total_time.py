from app.strategy.base import DispatchStrategy


class MinTotalTimeStrategy(DispatchStrategy):
    """Assign to pile with shortest (waiting_time + own_charge_time)."""

    async def dispatch(self, candidates, piles, context):
        if not candidates or not piles:
            return {}

        assignments = {}
        for candidate in candidates:
            mode = candidate.mode if hasattr(candidate, 'mode') else candidate.get('mode')
            requested_kwh = candidate.requested_kwh if hasattr(candidate, 'requested_kwh') else candidate.get('requested_kwh')
            order_id = candidate.id if hasattr(candidate, 'id') else candidate.get('id')

            same_mode_piles = [p for p in piles if _p_mode(p) == mode]
            if not same_mode_piles:
                continue

            best_pile = None
            min_time = float('inf')

            for pile in same_mode_piles:
                power_rate = pile.power_rate if hasattr(pile, 'power_rate') else pile.get('power_rate')
                queue_entries = context.get('pile_queues', {}).get(_p_id(pile), [])
                waiting_time = 0.0
                for entry in queue_entries:
                    entry_kwh = entry.get('requested_kwh', 0)
                    waiting_time += entry_kwh / power_rate
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
