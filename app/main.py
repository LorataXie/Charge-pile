from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, func
from app.dependencies import engine, async_session_factory
from app.models import Base
from app.models.billing_rule import BillingRule, PeriodType
from app.models.charging_pile import ChargingPile, PileStatus
from app.models.charging_order import ChargingOrder
from app.models.pile_queue import PileQueue
from app.models.waiting_queue import WaitingQueue
from app.simulation.clock import clock
from app.controllers import (
    user_controller, charging_controller, queue_controller,
    pile_controller, billing_controller, fault_controller,
    report_controller, sim_controller, vehicle_controller
)
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        await session.execute(delete(BillingRule))
        rules_data = [
            BillingRule(period_type=PeriodType.PEAK, price_per_kwh=1.0, service_fee_per_kwh=0.8, start_hour=10, end_hour=15, description="峰时 10:00-15:00"),
            BillingRule(period_type=PeriodType.PEAK, price_per_kwh=1.0, service_fee_per_kwh=0.8, start_hour=18, end_hour=21, description="峰时 18:00-21:00"),
            BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=7, end_hour=10, description="平时 7:00-10:00"),
            BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=15, end_hour=18, description="平时 15:00-18:00"),
            BillingRule(period_type=PeriodType.NORMAL, price_per_kwh=0.7, service_fee_per_kwh=0.8, start_hour=21, end_hour=23, description="平时 21:00-23:00"),
            BillingRule(period_type=PeriodType.VALLEY, price_per_kwh=0.4, service_fee_per_kwh=0.8, start_hour=23, end_hour=24, description="谷时 23:00-24:00"),
            BillingRule(period_type=PeriodType.VALLEY, price_per_kwh=0.4, service_fee_per_kwh=0.8, start_hour=0, end_hour=7, description="谷时 0:00-7:00"),
        ]
        for rule in rules_data:
            session.add(rule)

        result = await session.execute(select(func.count(ChargingPile.id)))
        count = result.scalar()
        if count == 0:
            for i in range(settings.FAST_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"F{i+1}", mode="F", power_rate=settings.FAST_POWER_RATE, status=PileStatus.IDLE))
            for i in range(settings.SLOW_PILE_COUNT):
                session.add(ChargingPile(pile_code=f"T{i+1}", mode="T", power_rate=settings.SLOW_POWER_RATE, status=PileStatus.IDLE))

        await session.commit()

        time_candidates = []
        for model, column in [
            (WaitingQueue, WaitingQueue.entered_at),
            (PileQueue, PileQueue.entered_at),
            (ChargingOrder, ChargingOrder.end_time),
        ]:
            result = await session.execute(select(func.max(column)))
            value = result.scalar()
            if value:
                time_candidates.append(value)
        if time_candidates:
            clock.set(max(time_candidates))
    yield


app = FastAPI(
    title="智能充电站调度计费系统",
    description="BUPT 智能充电桩调度计费系统 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_controller.router)
app.include_router(charging_controller.router)
app.include_router(queue_controller.router)
app.include_router(pile_controller.router)
app.include_router(billing_controller.router)
app.include_router(fault_controller.router)
app.include_router(report_controller.router)
app.include_router(sim_controller.router)
app.include_router(vehicle_controller.router)


@app.get("/")
async def root():
    return {
        "system": "智能充电站调度计费系统",
        "version": "1.0.0",
        "docs": "/docs",
        "config": {
            "fast_piles": settings.FAST_PILE_COUNT,
            "slow_piles": settings.SLOW_PILE_COUNT,
            "fast_power": f"{settings.FAST_POWER_RATE}度/小时",
            "slow_power": f"{settings.SLOW_POWER_RATE}度/小时",
            "waiting_area_size": settings.WAITING_AREA_SIZE,
            "pile_queue_length": settings.PILE_QUEUE_LENGTH,
        }
    }
