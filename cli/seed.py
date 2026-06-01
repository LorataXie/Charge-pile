#!/usr/bin/env python3
"""种子数据脚本 - 一键生成管理员 + 25用户 + 车辆 + 充电站满载场景"""
import sys, asyncio
sys.path.insert(0, ".")

from app.dependencies import engine, async_session_factory
from app.models import Base
from app.services.user_service import UserService
from app.services.scheduling_service import SchedulingService
from app.simulation.clock import clock
from datetime import datetime


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.models.billing_rule import BillingRule, PeriodType
    from app.models.charging_pile import ChargingPile, PileStatus
    from app.models.vehicle import Vehicle
    from app.dao.vehicle_dao import VehicleDAO
    from config.settings import settings
    from sqlalchemy import select, func

    async with async_session_factory() as session:
        # ── 计费规则 ──
        count = (await session.execute(select(func.count(BillingRule.id)))).scalar()
        if count == 0:
            for pt, price, sh, eh, desc in [
                ("PEAK", 1.0, 10, 15, "峰时"), ("PEAK", 1.0, 18, 21, "峰时"),
                ("NORMAL", 0.7, 7, 10, "平时"), ("NORMAL", 0.7, 15, 18, "平时"),
                ("NORMAL", 0.7, 21, 23, "平时"), ("VALLEY", 0.4, 23, 24, "谷时"),
                ("VALLEY", 0.4, 0, 7, "谷时"),
            ]:
                session.add(BillingRule(period_type=PeriodType(pt), price_per_kwh=price,
                    service_fee_per_kwh=0.8, start_hour=sh, end_hour=eh, description=desc))

        # ── 充电桩 ──
        count = (await session.execute(select(func.count(ChargingPile.id)))).scalar()
        if count == 0:
            for i in range(settings.FAST_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"F{i+1}", mode="F", power_rate=settings.FAST_POWER_RATE, status=PileStatus.IDLE))
            for i in range(settings.SLOW_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"T{i+1}", mode="T", power_rate=settings.SLOW_POWER_RATE, status=PileStatus.IDLE))

        # ── 管理员 ──
        us = UserService(session)
        try:
            await us.register("admin", "admin123", "admin")
        except ValueError:
            pass

        # ── 25 个普通用户 ──
        users = {}
        for i in range(1, 26):
            try:
                u = await us.register(f"user{i}", "user123", "client")
                users[i] = u.id
            except ValueError:
                users[i] = i
        await session.commit()

    # ── 车辆 ──
    async with async_session_factory() as session:
        vdao = VehicleDAO(session)
        vehicles = {}
        plates = [
            "京A BU556","京B PT228","京C EM339","京D RA441","京E WS552",
            "京F ND663","京G JK774","京H XF885","京J ZQ996","京K HY107",
            "京L VC218","京M TQ329","京N PX430","京P LK541","京Q GT652",
            "京R DY763","京S AB874","京T CD985","京U EF096","京V GH187",
            "京W IJ278","京X KL369","京Y MN470","京Z OP581","京A QR692",
        ]
        for i in range(1, 26):
            existing = await vdao.get_by_user_id(users[i])
            if not existing:
                v = await vdao.create(Vehicle(
                    user_id=users[i],
                    license_plate=plates[i-1],
                    battery_capacity=50.0 + (i % 10) * 10,
                ))
                vehicles[i] = v.id
            else:
                vehicles[i] = existing[0].id
        await session.commit()

    # ── 充电请求（极端不均衡负载，展现 MinTotalTime 策略）──
    # 设计思路：
    #   F3 全是轻量车(5~8度) → 0.6h 就能清空队列
    #   F1 积压大电量(80~50度) → 6.3h 等待
    #   T2 全是轻量车(5~10度) → 2.0h
    #   T1 积压大电量(30~15度) → 6.5h
    # 新车提交时，策略自动避开重载桩，优选轻载桩。
    # Tick 推进后，轻载桩先空出位置，等候区车辆优先入轻载桩。
    async with async_session_factory() as session:
        ss = SchedulingService(session)
        clock.set(datetime(2026, 5, 31, 9, 0, 0))

        # 策略演示：每辆车都选"等待时间+自己充电时间"最短的桩
        #
        # 场景设计：
        #   1. user1 200kWh 大电量 → F1 (所有桩空, 选第一个)   F1=6.67h
        #   2. user2   5kWh 小电量 → F2 (F1=6.67h, F2/F3=0)  F2=0.17h
        #   3. user3   5kWh 小电量 → F3 (F2已有车, F3空)     F3=0.17h
        #   → 每辆车都在避开重载桩，选择最轻的！
        #
        # 之后逐渐填满所有桩，溢出进等候区
        requests = [
            # ── 快充演示组（极端对比）──
            (1,  "F", 200, "F1:200kWh,重载!"),
            (2,  "F",   5, "F2:避开重F1(6.7h),选空的F2"),
            (3,  "F",   5, "F3:避开F1(6.7h)和F2(0.2h),选空的F3"),
            # ── 填满快充桩 ──
            (4,  "F",  20, ""),
            (5,  "F",  15, ""),
            (6,  "F",  10, ""),
            (7,  "F",  25, ""),
            (8,  "F",  30, ""),
            (9,  "F",  35, ""),
            # ── 快充溢出 → 等候区 ──
            (10, "F",  20, "等候区(9个快充位已满)"),
            (11, "F",  15, ""),
            (12, "F",  25, ""),
            (13, "F",  10, ""),
            # ── 慢充演示组 ──
            (14, "T",  60, "T1:60kWh,重载!"),
            (15, "T",   5, "T2:避开重T1(6h),选空的T2"),
            # ── 填满慢充桩 ──
            (16, "T",  20, ""),
            (17, "T",  10, ""),
            (18, "T",  15, ""),
            (19, "T",   8, ""),
            # ── 慢充溢出 → 等候区 ──
            (20, "T",  12, "等候区(6个慢充位已满)"),
            (21, "T",   8, ""),
        ]

        print()
        print("  调度决策过程（MinTotalTime = 等待时间 + 自己充电时间）:")
        print("  ─────────────────────────────────────────────")

        stats = {"CHARGING": 0, "QUEUED": 0, "WAITING": 0}
        for item in requests:
            uid_idx, mode, kwh = item[0], item[1], item[2]
            note = item[3] if len(item) > 3 else ""
            try:
                order = await ss.submit_request(
                    user_id=users[uid_idx], vehicle_id=vehicles[uid_idx],
                    mode=mode, requested_kwh=kwh)
                st = order.status.value
                stats[st] = stats.get(st, 0) + 1
                pile_info = f"→桩{order.pile_id}" if order.pile_id else ""
                status_info = f"[{st}]"
                note_str = f"  ← {note}" if note else ""
                print(f"  {order.queue_number}: user{uid_idx} {kwh}度 {status_info:12s} {pile_info:5s}{note_str}")
            except Exception as e:
                print(f"  订单失败: user{uid_idx} {e}")
        print("  ─────────────────────────────────────────────")
        await session.commit()

    # 打印各桩负载
    async with async_session_factory() as session:
        from app.dao.queue_dao import QueueDAO
        from app.dao.pile_dao import PileDAO
        from app.dao.order_dao import OrderDAO
        qd, pd, od = QueueDAO(session), PileDAO(session), OrderDAO(session)

        print()
        print("  当前各桩队列:")
        for code, pid in [("F1",1),("F2",2),("F3",3),("T1",4),("T2",5)]:
            pile = await pd.get_by_id(pid)
            entries = await qd.get_pile_queue_entries(pid)
            total = 0; labels = []
            for e in entries:
                o = await od.get_by_id(e.order_id)
                k = o.requested_kwh if o else 0
                total += k; labels.append(f"{k:.0f}度")
            wait_h = total / pile.power_rate
            print(f"  {code} ({pile.power_rate:.0f}度/h): {'+'.join(labels)}={total:.0f}度 → 等待 {wait_h:.1f}h")

    print("=" * 55)
    print("  种子数据初始化完成")
    print("=" * 55)
    print(f"  充电中: {stats.get('CHARGING',0)} | 排队中: {stats.get('QUEUED',0)} | 等候区: {stats.get('WAITING',0)}")
    print()
    print("  账号汇总: admin(admin123) + user1~25(user123)")
    print()
    print("  演示 MinTotalTime 策略:")
    print("  1. admin -> 仿真控制 -> 推 Tick 让轻载桩先空出")
    print("  2. 观察等候区车辆被调度到等待时间最短的桩")
    print("  3. admin -> 故障管理 -> 上报故障看重调度")


if __name__ == "__main__":
    asyncio.run(seed())
