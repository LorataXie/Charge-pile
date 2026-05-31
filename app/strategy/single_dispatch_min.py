from itertools import permutations
from app.strategy.base import DispatchStrategy


class SingleDispatchMinTimeStrategy(DispatchStrategy):
    """When multiple slots open, enumerate assignments for min total completion time."""

    async def dispatch(self, candidates, piles, context):
        if not candidates or not piles:
            return {}

        n_candidates = len(candidates)
        if n_candidates == 0:
            return {}

        best_assignment = None
        min_total_time = float('inf')

        pile_ids = [_p_id(p) for p in piles]
        for perm in permutations(range(len(piles)), n_candidates):
            total_time = 0.0
            assignment = {}
            valid = True
            for cand_idx, pile_idx in enumerate(perm):
                candidate = candidates[cand_idx]
                pile = piles[pile_idx]
                cand_mode = candidate.mode if hasattr(candidate, 'mode') else candidate.get('mode')
                pile_mode = pile.mode if hasattr(pile, 'mode') else pile.get('mode')

                if cand_mode != pile_mode:
                    valid = False
                    break

                requested_kwh = candidate.requested_kwh if hasattr(candidate, 'requested_kwh') else candidate.get('requested_kwh')
                power_rate = pile.power_rate if hasattr(pile, 'power_rate') else pile.get('power_rate')
                order_id = candidate.id if hasattr(candidate, 'id') else candidate.get('id')

                queue_entries = context.get('pile_queues', {}).get(_p_id(pile), [])
                waiting_time = sum(e.get('requested_kwh', 0) / power_rate for e in queue_entries)
                own_time = requested_kwh / power_rate
                total_time += waiting_time + own_time
                assignment[order_id] = _p_id(pile)

            if valid and total_time < min_total_time:
                min_total_time = total_time
                best_assignment = assignment

        return best_assignment or {}


def _p_id(pile):
    return pile.id if hasattr(pile, 'id') else pile.get('id')
