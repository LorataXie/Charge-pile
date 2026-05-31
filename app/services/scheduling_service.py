from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.order_dao import OrderDAO
from app.dao.queue_dao import QueueDAO
from app.dao.pile_dao import PileDAO
from app.services.billing_service import BillingService
from app.services.pile_service import PileService
from app.strategy.min_total_time import MinTotalTimeStrategy
from app.strategy.priority_schedule import PriorityScheduleStrategy
from app.strategy.time_order_schedule import TimeOrderScheduleStrategy
from app.strategy.fault_recovery import FaultRecoveryStrategy
from app.strategy.single_dispatch_min import SingleDispatchMinTimeStrategy
from app.strategy.batch_dispatch_min import BatchDispatchMinTimeStrategy
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.waiting_queue import WaitingQueue
from app.models.pile_queue import PileQueue
from app.models.charging_pile import ChargingPile, PileStatus
from app.simulation.clock import clock
from config.settings import settings


class SchedulingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_dao = OrderDAO(session)
        self.queue_dao = QueueDAO(session)
        self.pile_dao = PileDAO(session)
        self.billing_service = BillingService(session)
        self.pile_service = PileService(session)
        self._next_f_seq = {mode: 0 for mode in ['F', 'T']}
        self.default_strategy = MinTotalTimeStrategy()

    async def submit_request(self, user_id: int, vehicle_id: int, mode: str, requested_kwh: float) -> ChargingOrder:
        waiting_count = len(await self.queue_dao.get_waiting_by_mode(mode))
        if waiting_count >= settings.WAITING_AREA_SIZE:
            raise ValueError("等候区已满，无法提交请求")

        if mode not in ('F', 'T'):
            raise ValueError("充电模式必须为 F(快充) 或 T(慢充)")

        max_num = await self.order_dao.get_max_queue_number_for_mode(mode)
        queue_number = f"{mode}{max_num + 1}"

        order = ChargingOrder(
            user_id=user_id,
            vehicle_id=vehicle_id,
            queue_number=queue_number,
            mode=mode,
            requested_kwh=requested_kwh,
            status=OrderStatus.WAITING,
        )
        order = await self.order_dao.create(order)

        position = waiting_count + 1
        waiting_entry = WaitingQueue(
            order_id=order.id,
            queue_number=queue_number,
            mode=mode,
            position=position,
            entered_at=clock.now,
        )
        await self.queue_dao.add_to_waiting(waiting_entry)

        await self._try_dispatch()
        return order

    async def modify_request(self, order_id: int, new_mode: str | None = None, new_kwh: float | None = None) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.status in (OrderStatus.QUEUED, OrderStatus.CHARGING):
            if new_mode is not None:
                raise ValueError("已在充电区，无法修改充电模式，请先取消后重新提交")
            if new_kwh is not None:
                raise ValueError("已在充电区，无法修改充电量，请先取消后重新提交")

        if new_mode is not None and order.status == OrderStatus.WAITING:
            await self.queue_dao.remove_from_waiting(order.id)
            max_num = await self.order_dao.get_max_queue_number_for_mode(new_mode)
            new_qn = f"{new_mode}{max_num + 1}"
            order.queue_number = new_qn
            order.mode = new_mode

            waiting_count = len(await self.queue_dao.get_waiting_by_mode(new_mode))
            waiting_entry = WaitingQueue(
                order_id=order.id,
                queue_number=new_qn,
                mode=new_mode,
                position=waiting_count + 1,
                entered_at=clock.now,
            )
            await self.queue_dao.add_to_waiting(waiting_entry)

        if new_kwh is not None:
            order.requested_kwh = new_kwh

        await self.order_dao.update(order)
        await self._try_dispatch()
        return order

    async def cancel_request(self, order_id: int) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.status in (OrderStatus.WAITING,):
            await self.queue_dao.remove_from_waiting(order.id)
        elif order.status in (OrderStatus.QUEUED, OrderStatus.CHARGING):
            pile_entry = await self.queue_dao.get_pile_queue_by_order(order.id)
            if pile_entry:
                await self.queue_dao.remove_from_pile_queue(order.id)
                await self.queue_dao.reorder_pile_queue_positions(order.pile_id)

        order.status = OrderStatus.CANCELLED
        order.end_time = clock.now
        await self.order_dao.update(order)
        await self._try_dispatch()
        return order

    async def end_charging(self, order_id: int) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        pile = await self.pile_dao.get_by_id(order.pile_id)
        order.end_time = clock.now
        order.status = OrderStatus.COMPLETED

        detail = await self.billing_service.calculate_billing(order, pile.power_rate)
        await self.billing_service.save_detail(detail)

        duration_hours = (order.end_time - order.start_time).total_seconds() / 3600
        actual_kwh = detail.total_kwh
        await self.pile_service.increment_stats(pile.id, duration_hours, actual_kwh)

        pile_entry = await self.queue_dao.get_pile_queue_by_order(order.id)
        if pile_entry:
            await self.queue_dao.remove_from_pile_queue(order.id)
            await self.queue_dao.reorder_pile_queue_positions(pile.id)

        await self.order_dao.update(order)
        await self._promote_next_in_pile(pile.id)
        await self._try_dispatch()
        return order

    async def _promote_next_in_pile(self, pile_id: int) -> None:
        entries = await self.queue_dao.get_pile_queue_entries(pile_id)
        if entries:
            first = entries[0]
            if not first.is_charging:
                first.is_charging = True
                order = await self.order_dao.get_by_id(first.order_id)
                if order:
                    order.status = OrderStatus.CHARGING
                    order.start_time = clock.now
                    await self.order_dao.update(order)
                self.session.add(first)
                await self.session.flush()

    async def _try_dispatch(self) -> None:
        for mode in ('F', 'T'):
            all_piles = await self.pile_dao.get_available_by_mode(mode)
            for pile in all_piles:
                queue_size = await self.queue_dao.get_pile_queue_size(pile.id)
                while queue_size < settings.PILE_QUEUE_LENGTH:
                    next_waiting = await self.queue_dao.get_next_in_waiting(mode)
                    if not next_waiting:
                        break
                    await self._dispatch_to_pile(next_waiting.order_id, pile.id)
                    queue_size = await self.queue_dao.get_pile_queue_size(pile.id)

    async def _dispatch_to_pile(self, order_id: int, pile_id: int) -> None:
        order = await self.order_dao.get_by_id(order_id)
        pile = await self.pile_dao.get_by_id(pile_id)
        if not order or not pile:
            return

        await self.queue_dao.remove_from_waiting(order.id)

        queue_size = await self.queue_dao.get_pile_queue_size(pile_id)
        is_first = (queue_size == 0)
        now = clock.now

        entry = PileQueue(
            order_id=order.id,
            pile_id=pile_id,
            position=queue_size + 1,
            is_charging=is_first,
            entered_at=now,
        )
        await self.queue_dao.add_to_pile_queue(entry)

        if is_first:
            order.status = OrderStatus.CHARGING
            order.start_time = now
        else:
            order.status = OrderStatus.QUEUED
        order.pile_id = pile_id
        order.queue_position = queue_size + 1
        await self.order_dao.update(order)

        if not is_first:
            pile.status = PileStatus.CHARGING
            await self.pile_dao.update(pile)

    async def handle_fault(self, pile_id: int, strategy_type: str) -> dict:
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")

        mode = pile.mode
        charging_entry = await self.queue_dao.get_pile_charging_entry(pile_id)

        if charging_entry:
            charge_order = await self.order_dao.get_by_id(charging_entry.order_id)
            if charge_order:
                charge_order.end_time = clock.now
                charge_order.status = OrderStatus.FAULT_INTERRUPTED
                detail = await self.billing_service.calculate_billing(
                    charge_order, pile.power_rate, is_fault_interrupted=True
                )
                await self.billing_service.save_detail(detail)
                await self.order_dao.update(charge_order)

        await self.pile_service.mark_broken(pile_id)

        remaining = await self.queue_dao.get_pile_queue_entries(pile_id)
        affected_orders = []
        for entry in remaining:
            if not entry.is_charging:
                order = await self.order_dao.get_by_id(entry.order_id)
                if order:
                    affected_orders.append(order)
        for entry in remaining:
            await self.queue_dao.remove_from_pile_queue(entry.order_id)

        await self.queue_dao.set_waiting_paused(True)

        if strategy_type == "PRIORITY":
            strategy = PriorityScheduleStrategy()
        elif strategy_type == "TIME_ORDER":
            strategy = TimeOrderScheduleStrategy()
        else:
            strategy = PriorityScheduleStrategy()

        if affected_orders:
            same_mode_piles = await self.pile_dao.get_available_by_mode(mode)
            same_mode_piles = [p for p in same_mode_piles if p.status != PileStatus.BROKEN]

            pile_queues = {}
            for p in same_mode_piles:
                entries = await self.queue_dao.get_pile_queue_entries(p.id)
                pile_queues[p.id] = [
                    {
                        "requested_kwh": (await self.order_dao.get_by_id(e.order_id)).requested_kwh
                    }
                    for e in entries
                ]

            context = {"pile_queues": pile_queues, "queue_len": settings.PILE_QUEUE_LENGTH}
            assignments = await strategy.dispatch(affected_orders, same_mode_piles, context)

            for order in affected_orders:
                assigned_pile_id = assignments.get(order.id)
                if assigned_pile_id:
                    await self._dispatch_to_pile(order.id, assigned_pile_id)

        return {"affected_count": len(affected_orders), "strategy": strategy_type}

    async def handle_fault_recovery(self, pile_id: int) -> dict:
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")

        mode = pile.mode
        await self.pile_service.mark_idle(pile_id)

        same_mode_piles = await self.pile_dao.get_available_by_mode(mode)

        await self.queue_dao.set_waiting_paused(True)
        strategy = FaultRecoveryStrategy()

        all_unstarted = []
        for p in same_mode_piles:
            entries = await self.queue_dao.get_pile_queue_entries(p.id)
            for entry in entries:
                if not entry.is_charging:
                    order = await self.order_dao.get_by_id(entry.order_id)
                    if order:
                        all_unstarted.append(order)
                    await self.queue_dao.remove_from_pile_queue(entry.order_id)

        if all_unstarted:
            pile_queues = {}
            for p in same_mode_piles:
                entries = [
                    e for e in await self.queue_dao.get_pile_queue_entries(p.id)
                    if e.is_charging
                ]
                pile_queues[p.id] = [
                    {
                        "requested_kwh": (await self.order_dao.get_by_id(e.order_id)).requested_kwh
                    }
                    for e in entries
                ]

            context = {"pile_queues": pile_queues, "queue_len": settings.PILE_QUEUE_LENGTH}
            assignments = await strategy.dispatch(all_unstarted, same_mode_piles, context)

            for order in all_unstarted:
                assigned_pile_id = assignments.get(order.id)
                if assigned_pile_id:
                    await self._dispatch_to_pile(order.id, assigned_pile_id)

        await self.queue_dao.set_waiting_paused(False)
        await self._try_dispatch()
        return {"redistributed": len(all_unstarted)}

    async def dispatch_from_waiting_area(self) -> int:
        dispatched = 0
        for mode in ('F', 'T'):
            piles = await self.pile_dao.get_available_by_mode(mode)
            for pile in piles:
                q_size = await self.queue_dao.get_pile_queue_size(pile.id)
                while q_size < settings.PILE_QUEUE_LENGTH:
                    next_w = await self.queue_dao.get_next_in_waiting(mode)
                    if not next_w:
                        break
                    await self._dispatch_to_pile(next_w.order_id, pile.id)
                    dispatched += 1
                    q_size = await self.queue_dao.get_pile_queue_size(pile.id)
        return dispatched

    async def get_queue_status(self, order_id: int) -> dict:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        waiting = await self.queue_dao.get_waiting_by_order(order_id)
        pile_q = await self.queue_dao.get_pile_queue_by_order(order_id)

        waiting_count = 0
        if waiting:
            all_waiting = await self.queue_dao.get_waiting_by_mode(order.mode)
            waiting_count = sum(1 for w in all_waiting if w.position < waiting.position)
        elif pile_q:
            all_entries = await self.queue_dao.get_pile_queue_entries(pile_q.pile_id)
            waiting_count = sum(1 for e in all_entries if e.position < pile_q.position)

        return {
            "order_id": order_id,
            "queue_number": order.queue_number,
            "mode": order.mode,
            "status": order.status.value if hasattr(order.status, 'value') else order.status,
            "waiting_count_ahead": waiting_count,
            "pile_id": order.pile_id,
        }
