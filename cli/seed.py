#!/usr/bin/env python3
"""种子数据脚本 - 一键生成管理员 + 测试用户 + 车辆 + 充电请求"""
import sys
import asyncio

# Add project root to path
sys.path.insert(0, ".")

from app.dependencies import engine, async_session_factory
from app.models import Base
from app.services.user_service import UserService
from app.services.scheduling_service import SchedulingService
from app.simulation.clock import clock
from datetime import datetime


async def seed():
    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ──── 计费规则 + 充电桩 ────
    from app.models.billing_rule import BillingRule, PeriodType
    from app.models.charging_pile import ChargingPile, PileStatus
    from config.settings import settings
    from sqlalchemy import select, func

    async with async_session_factory() as session:
        # 计费规则
        count = (await session.execute(select(func.count(BillingRule.id)))).scalar()
        if count == 0:
            rules = [
                BillingRule(period_type=PeriodType.PEAK, price_per_kwh=1.0, service_fee_per_kwh=0.8, start_hour=10, end_hour=15, description="峰时"),
                BillingRule(period_type=PeriodType.PEAK, price_per_kwh=1.0, service_fee_per_kwh=0.8, start_hour=18, end_hour=21, description="峰时"),
                BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=7, end_hour=10, description="平时"),
                BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=15, end_hour=18, description="平时"),
                BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=21, end_hour=23, description="平时"),
                BillingRule(period_type=PeriodType.VALLEY, price_per_kwh=0.4, service_fee_per_kwh=0.8, start_hour=23, end_hour=24, description="谷时"),
                BillingRule(period_type=PeriodType.VALLEY, price_per_kwh=0.4, service_fee_per_kwh=0.8, start_hour=0, end_hour=7, description="谷时"),
            ]
            for r in rules:
                session.add(r)
            print("  计费规则已创建 (7条)")

        # 充电桩
        count = (await session.execute(select(func.count(ChargingPile.id)))).scalar()
        if count == 0:
            for i in range(settings.FAST_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"F{i+1}", mode="F", power_rate=settings.FAST_POWER_RATE, status=PileStatus.IDLE))
            for i in range(settings.SLOW_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"T{i+1}", mode="T", power_rate=settings.SLOW_POWER_RATE, status=PileStatus.IDLE))
            print("  充电桩已创建 (3个快充 F1-F3, 2个慢充 T1-T2)")

        await session.commit()
        us = UserService(session)

        # ──── 管理员 ────
        try:
            await us.register("admin", "admin123", "admin")
            print("  admin (admin) - 管理员")
        except ValueError:
            print("  admin (admin) - 管理员 (已存在，跳过)")

        # ──── 5个普通用户 ────
        users = {}
        for i in range(1, 6):
            try:
                u = await us.register(f"user{i}", "user123", "client")
                users[i] = u.id
                print(f"  user{i} (client) - 普通用户")
            except ValueError:
                print(f"  user{i} (client) - 已存在，跳过")

        await session.commit()

    # ──── 创建车辆 ────
    from app.dao.vehicle_dao import VehicleDAO
    from app.models.vehicle import Vehicle

    async with async_session_factory() as session:
        vdao = VehicleDAO(session)
        vehicles = {}
        for i in range(1, 6):
            existing = await vdao.get_by_user_id(users.get(i, i + 1))
            if not existing:
                v = await vdao.create(Vehicle(
                    user_id=users.get(i, i + 1),
                    license_plate=f"京A{1000 + i}",
                    battery_capacity=50.0 + i * 10,
                ))
                vehicles[i] = v.id
                print(f"  车辆 京A{1000+i} (user{i}, {50+i*10}度)")
            else:
                vehicles[i] = existing[0].id
        await session.commit()

    # ──── 充电请求 ────
    async with async_session_factory() as session:
        ss = SchedulingService(session)

        # 设置虚拟时钟为当前时间（谷时→峰时过渡，方便测试分时计费）
        clock.set(datetime(2026, 5, 31, 9, 0, 0))

        requests = [
            (1, "F", 30.0),   # user1: 快充30度 → F1 充电中
            (2, "T", 15.0),   # user2: 慢充15度 → T1 充电中
            (3, "F", 20.0),   # user3: 快充20度 → F1 排队
            (4, "T", 10.0),   # user4: 慢充10度 → T1 排队
            (5, "F", 25.0),   # user5: 快充25度 → F2 充电中
        ]

        for uid_idx, mode, kwh in requests:
            try:
                order = await ss.submit_request(
                    user_id=users[uid_idx],
                    vehicle_id=vehicles[uid_idx],
                    mode=mode,
                    requested_kwh=kwh,
                )
                print(f"  订单 {order.queue_number}: user{uid_idx} {mode}模式 {kwh}度 → {order.status.value}")
            except Exception as e:
                print(f"  订单失败: {e}")

        await session.commit()

    print("\n  [OK] 种子数据初始化完成!")
    print()
    print("  ┌──────────┬──────────────┬──────────┐")
    print("  │ 账号     │ 密码         │ 角色     │")
    print("  ├──────────┼──────────────┼──────────┤")
    print("  │ admin    │ admin123     │ 管理员   │")
    print("  │ user1    │ user123      │ 客户     │")
    print("  │ user2    │ user123      │ 客户     │")
    print("  │ user3    │ user123      │ 客户     │")
    print("  │ user4    │ user123      │ 客户     │")
    print("  │ user5    │ user123      │ 客户     │")
    print("  └──────────┴──────────────┴──────────┘")


if __name__ == "__main__":
    asyncio.run(seed())
