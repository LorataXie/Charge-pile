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
            "京A0011","京A0022","京A0033","京A0044","京A0055",
            "京A0066","京A0077","京A0088","京A0099","京A0100",
            "京A0111","京A0122","京A0133","京A0144","京A0155",
            "京A0166","京A0177","京A0188","京A0199","京A0200",
            "京A0211","京A0222","京A0233","京A0244","京A0255",
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

    # ── 充电请求（按顺序提交，先到先得 → 溢出到等候区）──
    # 每桩队列长度 M=3，3个快充桩 = 9 快充位，2个慢充桩 = 6 慢充位
    # 提交 13 快充 + 8 慢充 → 快充多 4 个进等候区，慢充多 2 个进等候区
    async with async_session_factory() as session:
        ss = SchedulingService(session)
        clock.set(datetime(2026, 5, 31, 9, 0, 0))

        fast_requests = [
            (i, "F", 20.0 + (i % 5) * 5) for i in range(1, 14)  # user1~13, 20~40度
        ]
        slow_requests = [
            (i, "T", 8.0 + (i % 4) * 4) for i in range(14, 22)  # user14~21, 8~20度
        ]
        all_requests = fast_requests + slow_requests

        stats = {"CHARGING": 0, "QUEUED": 0, "WAITING": 0}

        for uid_idx, mode, kwh in all_requests:
            try:
                order = await ss.submit_request(
                    user_id=users[uid_idx],
                    vehicle_id=vehicles[uid_idx],
                    mode=mode,
                    requested_kwh=kwh,
                )
                st = order.status.value
                stats[st] = stats.get(st, 0) + 1
            except Exception as e:
                print(f"  订单失败: user{uid_idx} {e}")

        await session.commit()

    print("=" * 55)
    print("  智能充电站调度计费系统 - 种子数据初始化完成")
    print("=" * 55)
    print(f"  充电中: {stats.get('CHARGING', 0)}  排队中: {stats.get('QUEUED', 0)}  等候区: {stats.get('WAITING', 0)}")
    print()
    print("  ┌──────────────┬──────────────────────────────────┐")
    print("  │ 充电桩队列   │ F1/F2/F3 (各3位)  T1/T2 (各3位) │")
    print("  │ 等候区       │ 容量 N = 10                      │")
    print("  └──────────────┴──────────────────────────────────┘")
    print()
    print("  ┌──────────┬──────────┬──────────────────────────┐")
    print("  │ 账号     │ 密码     │ 说明                     │")
    print("  ├──────────┼──────────┼──────────────────────────┤")
    print("  │ admin    │ admin123 │ 管理员 - 全部管理功能    │")
    print("  │ user1    │ user123  │ 快充 - 充电桩队列中      │")
    print("  │ user2    │ user123  │ 快充 - 充电桩队列中      │")
    print("  │ ...      │ user123  │ user1~13 快充区         │")
    print("  │ user14   │ user123  │ 慢充 - 充电桩队列中      │")
    print("  │ ...      │ user123  │ user14~21 慢充区         │")
    print("  │ user22~25│ user123  │ 闲置（可注册后提交请求）  │")
    print("  └──────────┴──────────┴──────────────────────────┘")
    print()
    print("  演示流程:")
    print("  1. admin 登录 → 仿真控制 → Tick 推进时间")
    print("  2. user1 登录 → 我的订单 → 查看状态变化")
    print("  3. admin → 等候区 Tab → 查看排队车辆")
    print("  4. admin → 故障管理 → 上报桩故障看重调度")
    print("  5. admin → 报表 → 生成日报")


if __name__ == "__main__":
    asyncio.run(seed())
