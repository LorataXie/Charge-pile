#!/usr/bin/env python3
"""种子数据脚本 - 初始化可展示排队与调度策略的验收演示数据。"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, ".")

from app.dependencies import engine, async_session_factory
from app.models import Base
from app.models.billing_rule import BillingRule, PeriodType
from app.models.charging_pile import ChargingPile, PileStatus
from app.models.vehicle import Vehicle
from app.services.user_service import UserService
from app.services.scheduling_service import SchedulingService
from app.simulation.clock import clock
from config.settings import settings


BILLING_RULES = [
    (PeriodType.PEAK, 1.0, 10, 15, "峰时 10:00-15:00"),
    (PeriodType.PEAK, 1.0, 18, 21, "峰时 18:00-21:00"),
    (PeriodType.NORMAL, 0.7, 7, 10, "平时 7:00-10:00"),
    (PeriodType.NORMAL, 0.7, 15, 18, "平时 15:00-18:00"),
    (PeriodType.NORMAL, 0.7, 21, 23, "平时 21:00-23:00"),
    (PeriodType.VALLEY, 0.4, 23, 24, "谷时 23:00-24:00"),
    (PeriodType.VALLEY, 0.4, 0, 7, "谷时 0:00-7:00"),
]

VEHICLES = [
    (f"京A{1000 + i}", 50.0 + (i % 10) * 10)
    for i in range(1, 26)
]

REQUESTS = [
    (1, "F", 200.0),
    (2, "F", 5.0),
    (3, "F", 5.0),
    (4, "F", 20.0),
    (5, "F", 15.0),
    (6, "F", 10.0),
    (7, "F", 25.0),
    (8, "F", 30.0),
    (9, "F", 35.0),
    (10, "F", 20.0),
    (11, "F", 15.0),
    (12, "F", 25.0),
    (13, "F", 10.0),
    (14, "T", 60.0),
    (15, "T", 5.0),
    (16, "T", 20.0),
    (17, "T", 10.0),
    (18, "T", 15.0),
    (19, "T", 8.0),
    (20, "T", 12.0),
    (21, "T", 8.0),
]


async def reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def seed_reference_data() -> dict[int, int]:
    async with async_session_factory() as session:
        for period_type, price, start_hour, end_hour, description in BILLING_RULES:
            session.add(
                BillingRule(
                    period_type=period_type,
                    price_per_kwh=price,
                    service_fee_per_kwh=0.8,
                    start_hour=start_hour,
                    end_hour=end_hour,
                    description=description,
                )
            )

        for i in range(settings.FAST_PILE_COUNT):
            session.add(
                ChargingPile(
                    pile_code=f"F{i + 1}",
                    mode="F",
                    power_rate=settings.FAST_POWER_RATE,
                    status=PileStatus.IDLE,
                )
            )
        for i in range(settings.SLOW_PILE_COUNT):
            session.add(
                ChargingPile(
                    pile_code=f"T{i + 1}",
                    mode="T",
                    power_rate=settings.SLOW_POWER_RATE,
                    status=PileStatus.IDLE,
                )
            )

        user_service = UserService(session)
        await user_service.register("admin", "admin123", "admin")

        users: dict[int, int] = {}
        for i in range(1, 26):
            user = await user_service.register(f"user{i}", "user123", "client")
            users[i] = user.id

        await session.commit()
        return users


async def seed_vehicles(users: dict[int, int]) -> dict[int, int]:
    async with async_session_factory() as session:
        vehicles: dict[int, int] = {}
        for i, (license_plate, battery_capacity) in enumerate(VEHICLES, start=1):
            vehicle = Vehicle(
                user_id=users[i],
                license_plate=license_plate,
                battery_capacity=battery_capacity,
            )
            session.add(vehicle)
            await session.flush()
            vehicles[i] = vehicle.id

        await session.commit()
        return vehicles


async def seed_orders(users: dict[int, int], vehicles: dict[int, int]) -> None:
    async with async_session_factory() as session:
        scheduler = SchedulingService(session)
        clock.set(datetime(2026, 5, 31, 9, 0, 0))

        print()
        print("初始化充电订单:")
        stats = {"CHARGING": 0, "QUEUED": 0, "WAITING": 0}
        for user_idx, mode, requested_kwh in REQUESTS:
            order = await scheduler.submit_request(
                user_id=users[user_idx],
                vehicle_id=vehicles[user_idx],
                mode=mode,
                requested_kwh=requested_kwh,
            )
            stats[order.status.value] = stats.get(order.status.value, 0) + 1
            pile = f" -> 充电桩 {order.pile_id}" if order.pile_id else ""
            print(
                f"  {order.queue_number}: user{user_idx} "
                f"{mode} {requested_kwh:g}度 [{order.status.value}]{pile}"
            )

        await session.commit()
        print(
            f"订单状态: 充电中 {stats.get('CHARGING', 0)}，"
            f"桩内排队 {stats.get('QUEUED', 0)}，"
            f"等候区 {stats.get('WAITING', 0)}"
        )


async def seed() -> None:
    await reset_schema()
    users = await seed_reference_data()
    vehicles = await seed_vehicles(users)
    await seed_orders(users, vehicles)

    print("=" * 55)
    print("测试数据初始化完成")
    print("=" * 55)
    print("管理员: admin / admin123")
    print("客户: user1~user25 / user123")
    print("车辆: 京A1001~京A1025")
    print("订单: 21 条，包含 13 条快充 + 8 条慢充")


if __name__ == "__main__":
    asyncio.run(seed())
