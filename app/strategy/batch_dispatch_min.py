from app.strategy.base import DispatchStrategy


class BatchDispatchMinTimeStrategy(DispatchStrategy):
    """Global batch assignment ignoring mode distinction. All vehicles can go to any pile."""

    async def dispatch(self, candidates, piles, context):
        if not candidates or not piles:
            return {}

        sorted_candidates = sorted(
            candidates,
            key=lambda c: -(c.requested_kwh if hasattr(c, 'requested_kwh') else c.get('requested_kwh', 0))
        )

        pile_loads = {_p_id(p): 0.0 for p in piles}
        assignments = {}

        for candidate in sorted_candidates:
            requested_kwh = candidate.requested_kwh if hasattr(candidate, 'requested_kwh') else candidate.get('requested_kwh')
            order_id = candidate.id if hasattr(candidate, 'id') else candidate.get('id')

            best_pile_id = None
            min_total = float('inf')

            for pile in piles:
                pile_id = _p_id(pile)
                power_rate = pile.power_rate if hasattr(pile, 'power_rate') else pile.get('power_rate')
                current_load = pile_loads[pile_id]
                new_load = current_load + requested_kwh / power_rate
                if new_load < min_total:
                    min_total = new_load
                    best_pile_id = pile_id

            if best_pile_id is not None:
                assignments[order_id] = best_pile_id
                pile_loads[best_pile_id] = min_total

        return assignments


def _p_id(pile):
    return pile.id if hasattr(pile, 'id') else pile.get('id')
