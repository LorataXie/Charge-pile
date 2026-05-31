"""调度服务 — 核心业务逻辑。每个方法自备细粒度注释解释 WHY。"""
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
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.waiting_queue import WaitingQueue
from app.models.pile_queue import PileQueue
from app.models.charging_pile import ChargingPile, PileStatus
from app.simulation.clock import clock
from config.settings import settings


def _pile_id_of(pile): return pile.id if hasattr(pile, 'id') else pile.get('id')
def _pile_mode(pile): return pile.mode if hasattr(pile, 'mode') else pile.get('mode')
def _pile_rate(pile): return pile.power_rate if hasattr(pile, 'power_rate') else pile.get('power_rate')


def _calc_total_time(pile, order, existing_queue_kwh_list):
    """给定一辆车和一组排队车已请求度数，计算 等待时间+自己充电时间。"""
    waiting = sum(kwh / _pile_rate(pile) for kwh in existing_queue_kwh_list)
    own = order.requested_kwh / _pile_rate(pile)
    return waiting + own


def _extract_queue_num(qn: str) -> int:
    try: return int(qn[1:])
    except: return 0


class SchedulingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_dao = OrderDAO(session)
        self.queue_dao = QueueDAO(session)
        self.pile_dao = PileDAO(session)
        self.billing_service = BillingService(session)
        self.pile_service = PileService(session)

    # ─── helpers ──────────────────────────────────────────────

    def _now(self): return clock.now

    async def _get_pile_queue_kwh_list(self, pile_id: int) -> list[float]:
        entries = await self.queue_dao.get_pile_queue_entries(pile_id)
        kwh_list = []
        for e in entries:
            o = await self.order_dao.get_by_id(e.order_id)
            kwh_list.append(o.requested_kwh if o else 0)
        return kwh_list

    # ─── submit ───────────────────────────────────────────────

    async def submit_request(self, user_id: int, vehicle_id: int,
                             mode: str, requested_kwh: float) -> ChargingOrder:
        if mode not in ('F', 'T'):
            raise ValueError("充电模式必须为 F(快充) 或 T(慢充)")
        waiting_count = len(await self.queue_dao.get_waiting_by_mode(mode))
        if waiting_count >= settings.WAITING_AREA_SIZE:
            raise ValueError("等候区已满")

        max_num = await self.order_dao.get_max_queue_number_for_mode(mode)
        qn = f"{mode}{max_num + 1}"

        order = ChargingOrder(user_id=user_id, vehicle_id=vehicle_id,
                              queue_number=qn, mode=mode,
                              requested_kwh=requested_kwh, status=OrderStatus.WAITING)
        order = await self.order_dao.create(order)

        wq = WaitingQueue(order_id=order.id, queue_number=qn, mode=mode,
                          position=waiting_count + 1, entered_at=self._now())
        await self.queue_dao.add_to_waiting(wq)
        await self._strategy_dispatch()
        return order

    # ─── modify ───────────────────────────────────────────────

    async def modify_request(self, order_id: int, new_mode: str | None = None,
                             new_kwh: float | None = None) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        # 充电区（QUEUED / CHARGING）一律禁止修改
        if order.status in (OrderStatus.QUEUED, OrderStatus.CHARGING):
            if new_mode is not None:
                raise ValueError("已在充电区，无法修改充电模式，请先取消后重新提交")
            if new_kwh is not None:
                raise ValueError("已在充电区，无法修改充电量，请先取消后重新提交")

        # 等候区改模式 → 重新排号，排到新模式队尾
        if new_mode is not None and order.status == OrderStatus.WAITING:
            await self.queue_dao.remove_from_waiting(order.id)
            await self._reorder_waiting_positions(order.mode)
            max_num = await self.order_dao.get_max_queue_number_for_mode(new_mode)
            new_qn = f"{new_mode}{max_num + 1}"
            order.queue_number = new_qn
            order.mode = new_mode
            wc = len(await self.queue_dao.get_waiting_by_mode(new_mode))
            wq = WaitingQueue(order_id=order.id, queue_number=new_qn, mode=new_mode,
                              position=wc + 1, entered_at=self._now())
            await self.queue_dao.add_to_waiting(wq)

        # 等候区改电量 → 排队号不变
        if new_kwh is not None:
            order.requested_kwh = new_kwh

        await self.order_dao.update(order)
        await self._strategy_dispatch()
        return order

    # ─── cancel ───────────────────────────────────────────────

    async def cancel_request(self, order_id: int) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")
        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise ValueError("订单已结束，无法取消")

        was_charging = order.status == OrderStatus.CHARGING

        if order.status == OrderStatus.WAITING:
            await self.queue_dao.remove_from_waiting(order.id)
            await self._reorder_waiting_positions(order.mode)
        elif order.status in (OrderStatus.QUEUED, OrderStatus.CHARGING):
            pile_entry = await self.queue_dao.get_pile_queue_by_order(order.id)
            pile_id = order.pile_id
            if pile_entry:
                await self.queue_dao.remove_from_pile_queue(order.id)
                await self.queue_dao.reorder_pile_queue_positions(pile_id)

            # 如果正在充电，生成中断详单
            if was_charging and order.start_time:
                pile = await self.pile_dao.get_by_id(pile_id)
                order.end_time = self._now()
                detail = await self.billing_service.calculate_billing(
                    order, pile.power_rate, is_fault_interrupted=False)
                await self.billing_service.save_detail(detail)
                await self.pile_service.increment_stats(
                    pile.id, detail.charge_duration_hours, detail.total_kwh)

            # 提升队列中下一辆车
            if pile_id:
                await self._promote_next_in_pile(pile_id)

        order.status = OrderStatus.CANCELLED
        order.end_time = self._now()
        await self.order_dao.update(order)
        await self._strategy_dispatch()
        return order

    # ─── end charging ─────────────────────────────────────────

    async def end_charging(self, order_id: int) -> ChargingOrder:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")
        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED,
                            OrderStatus.FAULT_INTERRUPTED):
            raise ValueError(f"订单已结束（{order.status.value}），无法重复结束")

        pile = await self.pile_dao.get_by_id(order.pile_id)
        if not pile:
            raise ValueError("充电桩不存在")

        order.end_time = self._now()
        order.status = OrderStatus.COMPLETED

        detail = await self.billing_service.calculate_billing(order, pile.power_rate)
        await self.billing_service.save_detail(detail)

        await self.pile_service.increment_stats(
            pile.id, detail.charge_duration_hours, detail.total_kwh)

        pile_entry = await self.queue_dao.get_pile_queue_by_order(order.id)
        if pile_entry:
            await self.queue_dao.remove_from_pile_queue(order.id)
            await self.queue_dao.reorder_pile_queue_positions(pile.id)

        await self.order_dao.update(order)
        await self._promote_next_in_pile(pile.id)
        await self._strategy_dispatch()
        return order

    # ─── internal helpers ─────────────────────────────────────

    async def _promote_next_in_pile(self, pile_id: int) -> None:
        entries = await self.queue_dao.get_pile_queue_entries(pile_id)
        if not entries:
            # 队列空了 → 桩变 IDLE
            pile = await self.pile_dao.get_by_id(pile_id)
            if pile and pile.status == PileStatus.CHARGING:
                pile.status = PileStatus.IDLE
                await self.pile_dao.update(pile)
            return

        first = entries[0]
        if not first.is_charging:
            first.is_charging = True
            order = await self.order_dao.get_by_id(first.order_id)
            if order:
                order.status = OrderStatus.CHARGING
                order.start_time = self._now()
                await self.order_dao.update(order)
            self.session.add(first)
            await self.session.flush()

    async def _reorder_waiting_positions(self, mode: str) -> None:
        """等候区删除后重新编排 position，保证查询正确。"""
        entries = await self.queue_dao.get_waiting_by_mode(mode)
        for idx, e in enumerate(entries, start=1):
            e.position = idx
        await self.session.flush()

    # ─── strategy dispatch ────────────────────────────────────

    async def _strategy_dispatch(self) -> None:
        """使用 MinTotalTime 策略：对同模式所有有空位的桩，选总时长最短的分配。"""
        for mode in ('F', 'T'):
            available_piles = [
                p for p in await self.pile_dao.get_available_by_mode(mode)
                if p.status in (PileStatus.IDLE, PileStatus.CHARGING)
            ]
            if not available_piles:
                continue

            # 收集等候区该模式的所有订单
            waiting_entries = await self.queue_dao.get_waiting_by_mode(mode)
            # 过滤暂停
            waiting_entries = [w for w in waiting_entries if not w.is_paused]

            for w_entry in waiting_entries:
                # 找到有空位的桩
                candidates = []
                for pile in available_piles:
                    q_size = await self.queue_dao.get_pile_queue_size(pile.id)
                    if q_size < settings.PILE_QUEUE_LENGTH:
                        candidates.append(pile)

                if not candidates:
                    break

                order = await self.order_dao.get_by_id(w_entry.order_id)
                if not order:
                    continue

                # MinTotalTime：选 等待时间+自己充电时间 最短的桩
                best_pile = None
                best_time = float('inf')
                for pile in candidates:
                    kwh_list = await self._get_pile_queue_kwh_list(pile.id)
                    t = _calc_total_time(pile, order, kwh_list)
                    if t < best_time:
                        best_time = t
                        best_pile = pile

                if best_pile:
                    await self._dispatch_to_pile(order.id, best_pile.id)

    async def _dispatch_to_pile(self, order_id: int, pile_id: int) -> None:
        order = await self.order_dao.get_by_id(order_id)
        pile = await self.pile_dao.get_by_id(pile_id)
        if not order or not pile:
            return

        await self.queue_dao.remove_from_waiting(order.id)
        await self._reorder_waiting_positions(order.mode)

        q_size = await self.queue_dao.get_pile_queue_size(pile_id)
        is_first = (q_size == 0)
        now = self._now()

        entry = PileQueue(order_id=order.id, pile_id=pile_id,
                          position=q_size + 1, is_charging=is_first, entered_at=now)
        await self.queue_dao.add_to_pile_queue(entry)

        order.status = OrderStatus.CHARGING if is_first else OrderStatus.QUEUED
        order.pile_id = pile_id
        order.queue_position = q_size + 1
        if is_first:
            order.start_time = now
        await self.order_dao.update(order)

        # 桩状态：只要有车在队列中就是 CHARGING
        if pile.status == PileStatus.IDLE:
            pile.status = PileStatus.CHARGING
            await self.pile_dao.update(pile)

    # ─── fault handling ───────────────────────────────────────

    async def handle_fault(self, pile_id: int, strategy_type: str) -> dict:
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")

        mode = pile.mode

        # 1. 处理正在充电的车 → 生成中断详单
        charging_entry = await self.queue_dao.get_pile_charging_entry(pile_id)
        if charging_entry:
            charge_order = await self.order_dao.get_by_id(charging_entry.order_id)
            if charge_order and charge_order.status == OrderStatus.CHARGING:
                charge_order.end_time = self._now()
                charge_order.status = OrderStatus.FAULT_INTERRUPTED
                detail = await self.billing_service.calculate_billing(
                    charge_order, pile.power_rate, is_fault_interrupted=True)
                await self.billing_service.save_detail(detail)
                await self.order_dao.update(charge_order)

        # 2. 标记故障
        await self.pile_service.mark_broken(pile_id)

        # 3. 收集故障桩队列中所有订单（含刚中断的），全部移出
        all_entries = await self.queue_dao.get_pile_queue_entries(pile_id)
        affected_orders = []
        for e in all_entries:
            o = await self.order_dao.get_by_id(e.order_id)
            if o and o.status not in (OrderStatus.FAULT_INTERRUPTED, OrderStatus.COMPLETED):
                affected_orders.append(o)
            await self.queue_dao.remove_from_pile_queue(e.order_id)

        # 4. 暂停等候区叫号
        await self.queue_dao.set_waiting_paused(True)

        if not affected_orders:
            # 故障队列已空 → 直接恢复叫号
            await self.queue_dao.set_waiting_paused(False)
            await self._strategy_dispatch()
            return {"affected_count": 0, "strategy": strategy_type}

        same_mode_piles = [
            p for p in await self.pile_dao.get_available_by_mode(mode)
            if p.status != PileStatus.BROKEN
        ]

        if strategy_type == "TIME_ORDER":
            # 时间顺序：合并故障桩受影响订单 + 其他同类桩未充电订单，按排队号排序
            strategy = TimeOrderScheduleStrategy()
            for p in same_mode_piles:
                entries = await self.queue_dao.get_pile_queue_entries(p.id)
                for e in entries:
                    if not e.is_charging:
                        o = await self.order_dao.get_by_id(e.order_id)
                        if o and o not in affected_orders:
                            affected_orders.append(o)
                        await self.queue_dao.remove_from_pile_queue(e.order_id)
            affected_orders.sort(key=lambda o: _extract_queue_num(o.queue_number or ""))
        else:
            # 优先级：仅处理故障桩的受影响订单
            strategy = PriorityScheduleStrategy()

        # 构建上下文
        pile_queues = {}
        for p in same_mode_piles:
            entries = await self.queue_dao.get_pile_queue_entries(p.id)
            pile_queues[p.id] = [
                {"requested_kwh": (await self.order_dao.get_by_id(e.order_id)).requested_kwh}
                for e in entries if e.is_charging
            ]

        context = {"pile_queues": pile_queues, "queue_len": settings.PILE_QUEUE_LENGTH}
        assignments = await strategy.dispatch(affected_orders, same_mode_piles, context)

        for o in affected_orders:
            pid = assignments.get(o.id)
            if pid:
                await self._dispatch_to_pile(o.id, pid)

        # 5. 恢复等候区叫号
        await self.queue_dao.set_waiting_paused(False)
        await self._strategy_dispatch()
        return {"affected_count": len(affected_orders), "strategy": strategy_type}

    async def handle_fault_recovery(self, pile_id: int) -> dict:
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")

        mode = pile.mode
        await self.pile_service.mark_idle(pile_id)

        same_mode_piles = await self.pile_dao.get_available_by_mode(mode)
        strategy = FaultRecoveryStrategy()

        # 暂停叫号
        await self.queue_dao.set_waiting_paused(True)

        # 收集所有同类桩未充电订单
        all_unstarted = []
        for p in same_mode_piles:
            entries = await self.queue_dao.get_pile_queue_entries(p.id)
            for e in entries:
                if not e.is_charging:
                    o = await self.order_dao.get_by_id(e.order_id)
                    if o:
                        all_unstarted.append(o)
                    await self.queue_dao.remove_from_pile_queue(e.order_id)

        if all_unstarted:
            all_unstarted.sort(key=lambda o: _extract_queue_num(o.queue_number or ""))

            pile_queues = {}
            for p in same_mode_piles:
                entries = [
                    e for e in await self.queue_dao.get_pile_queue_entries(p.id)
                    if e.is_charging
                ]
                pile_queues[p.id] = [
                    {"requested_kwh": (await self.order_dao.get_by_id(e.order_id)).requested_kwh}
                    for e in entries
                ]

            context = {"pile_queues": pile_queues, "queue_len": settings.PILE_QUEUE_LENGTH}
            assignments = await strategy.dispatch(all_unstarted, same_mode_piles, context)

            for o in all_unstarted:
                pid = assignments.get(o.id)
                if pid:
                    await self._dispatch_to_pile(o.id, pid)

        # 恢复叫号
        await self.queue_dao.set_waiting_paused(False)
        await self._strategy_dispatch()
        return {"redistributed": len(all_unstarted)}

    async def dispatch_from_waiting_area(self) -> int:
        """仿真引擎调用的公共入口。"""
        before_f = len(await self.queue_dao.get_waiting_by_mode('F'))
        before_t = len(await self.queue_dao.get_waiting_by_mode('T'))
        before = before_f + before_t
        await self._strategy_dispatch()
        after_f = len(await self.queue_dao.get_waiting_by_mode('F'))
        after_t = len(await self.queue_dao.get_waiting_by_mode('T'))
        return before - (after_f + after_t)

    async def get_queue_status(self, order_id: int) -> dict:
        order = await self.order_dao.get_by_id(order_id)
        if not order:
            raise ValueError("订单不存在")

        waiting = await self.queue_dao.get_waiting_by_order(order_id)
        pile_q = await self.queue_dao.get_pile_queue_by_order(order_id)

        ahead = 0
        if waiting:
            all_w = await self.queue_dao.get_waiting_by_mode(order.mode)
            ahead = sum(1 for w in all_w if w.position < waiting.position)
        elif pile_q:
            all_e = await self.queue_dao.get_pile_queue_entries(pile_q.pile_id)
            ahead = sum(1 for e in all_e if e.position < pile_q.position)

        return {
            "order_id": order_id,
            "queue_number": order.queue_number,
            "mode": order.mode,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "waiting_count_ahead": ahead,
            "pile_id": order.pile_id,
        }
