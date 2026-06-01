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

    # ─── 7. 故障处理 ───────────────────────────────────────

    async def handle_fault(self, pile_id: int, strategy_type: str) -> dict:
        """7a 优先级 / 7b 时间顺序 调度"""
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        mode = pile.mode
        dispatch_log = []  # 记录每辆车的调度去向

        # ── 7. 正在充电的车 → 停止计费，生成详单 ──
        interrupted_qn = None
        interrupted_detail_id = None
        charging_entry = await self.queue_dao.get_pile_charging_entry(pile_id)
        if charging_entry:
            co = await self.order_dao.get_by_id(charging_entry.order_id)
            if co and co.status == OrderStatus.CHARGING:
                co.end_time = self._now()
                co.status = OrderStatus.FAULT_INTERRUPTED
                detail = await self.billing_service.calculate_billing(
                    co, pile.power_rate, is_fault_interrupted=True)
                await self.billing_service.save_detail(detail)
                await self.order_dao.update(co)
                interrupted_qn = co.queue_number
                dispatch_log.append({
                    "queue_number": co.queue_number,
                    "action": "充电中断",
                    "detail": f"已充{detail.total_kwh}度，生成详单#{detail.id}",
                    "from_pile": pile.pile_code,
                    "to_pile": None,
                })

        await self.pile_service.mark_broken(pile_id)

        # ── 收集故障桩队列所有订单（包括刚中断的），全部移出 ──
        all_entries = await self.queue_dao.get_pile_queue_entries(pile_id)
        affected = []
        for e in all_entries:
            o = await self.order_dao.get_by_id(e.order_id)
            if o and o.status not in (OrderStatus.FAULT_INTERRUPTED, OrderStatus.COMPLETED):
                affected.append(o)
            await self.queue_dao.remove_from_pile_queue(e.order_id)

        # ── 暂停等候区叫号 ──
        await self.queue_dao.set_waiting_paused(True)

        if not affected:
            await self.queue_dao.set_waiting_paused(False)
            await self._strategy_dispatch()
            return {"affected_count": 0, "strategy": strategy_type,
                    "interrupted_vehicle": interrupted_qn,
                    "dispatch_log": dispatch_log}

        same_mode_piles = [
            p for p in await self.pile_dao.get_available_by_mode(mode)
            if p.status != PileStatus.BROKEN
        ]

        merged_from_other_piles = []
        if strategy_type == "TIME_ORDER":
            # 7b: 合并 "其他同类型桩尚未充电车辆 + 故障队列车辆"，按排队号排序
            for p in same_mode_piles:
                entries = await self.queue_dao.get_pile_queue_entries(p.id)
                for e in entries:
                    if not e.is_charging:
                        o = await self.order_dao.get_by_id(e.order_id)
                        if o and o not in affected:
                            affected.append(o)
                            merged_from_other_piles.append(o.queue_number)
                        await self.queue_dao.remove_from_pile_queue(e.order_id)
            affected.sort(key=lambda o: _extract_queue_num(o.queue_number or ""))

        # ── 分配到有空位的同类型桩 ──
        unassigned = []
        for o in affected:
            best_pile = None
            best_time = float('inf')
            for p in same_mode_piles:
                q_size = await self.queue_dao.get_pile_queue_size(p.id)
                if q_size < settings.PILE_QUEUE_LENGTH:
                    kwh_list = await self._get_pile_queue_kwh_list(p.id)
                    t = _calc_total_time(p, o, kwh_list)
                    if t < best_time:
                        best_time = t
                        best_pile = p
            if best_pile:
                await self._dispatch_to_pile(o.id, best_pile.id)
                dispatch_log.append({
                    "queue_number": o.queue_number,
                    "action": f"调度至桩{best_pile.pile_code}",
                    "detail": f"{o.requested_kwh}度 → {best_pile.pile_code}桩(等待{best_time:.2f}h)",
                    "from_pile": pile.pile_code,
                    "to_pile": best_pile.pile_code,
                })
            else:
                unassigned.append(o)

        # ── 未分配的车插入等候区前列（优先于普通等候车）──
        if unassigned:
            existing = await self.queue_dao.get_waiting_by_mode(mode)
            shift = len(unassigned)
            for w in reversed(existing):
                w.position += shift
            await self.session.flush()
            for idx, o in enumerate(unassigned, start=1):
                wq = WaitingQueue(order_id=o.id, queue_number=o.queue_number or "",
                                  mode=o.mode, position=idx, entered_at=self._now())
                await self.queue_dao.add_to_waiting(wq)
                dispatch_log.append({
                    "queue_number": o.queue_number,
                    "action": "进入等候区",
                    "detail": f"同类桩已满，插入等候区第{idx}位(优先调度)",
                    "from_pile": pile.pile_code,
                    "to_pile": "等候区",
                })

        # ── 恢复等候区叫号 ──
        await self.queue_dao.set_waiting_paused(False)
        await self._strategy_dispatch()
        return {
            "affected_count": len(affected),
            "strategy": strategy_type,
            "unassigned": len(unassigned),
            "interrupted_vehicle": interrupted_qn,
            "merged_from_other_piles": merged_from_other_piles,
            "dispatch_log": dispatch_log,
        }

    async def handle_fault_recovery(self, pile_id: int) -> dict:
        """7c 故障恢复：同类型桩有排队车时才重分配"""
        pile = await self.pile_dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        mode = pile.mode
        await self.pile_service.mark_idle(pile_id)

        same_mode_piles = await self.pile_dao.get_available_by_mode(mode)

        # ── 检查是否有排队车辆需要重分配 ──
        all_unstarted = []
        for p in same_mode_piles:
            entries = await self.queue_dao.get_pile_queue_entries(p.id)
            for e in entries:
                if not e.is_charging:
                    o = await self.order_dao.get_by_id(e.order_id)
                    if o:
                        all_unstarted.append(o)

        if not all_unstarted:
            # 没有排队车 → 直接恢复，无需重分配
            await self._strategy_dispatch()
            return {"redistributed": 0}

        # ── 暂停叫号，合并所有未充电车按排队号重分 ──
        await self.queue_dao.set_waiting_paused(True)

        for p in same_mode_piles:
            entries = await self.queue_dao.get_pile_queue_entries(p.id)
            for e in entries:
                if not e.is_charging:
                    await self.queue_dao.remove_from_pile_queue(e.order_id)

        all_unstarted.sort(key=lambda o: _extract_queue_num(o.queue_number or ""))

        for o in all_unstarted:
            best_pile = None
            best_time = float('inf')
            for p in same_mode_piles:
                q_size = await self.queue_dao.get_pile_queue_size(p.id)
                if q_size < settings.PILE_QUEUE_LENGTH:
                    kwh_list = await self._get_pile_queue_kwh_list(p.id)
                    t = _calc_total_time(p, o, kwh_list)
                    if t < best_time:
                        best_time = t
                        best_pile = p
            if best_pile:
                await self._dispatch_to_pile(o.id, best_pile.id)

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
