from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import (
    get_pile_service, get_scheduling_service, get_db, get_current_user, get_current_admin
)
from app.schemas import PileResponse, PileWithVehicles, MessageResponse
from app.services.pile_service import PileService
from app.services.scheduling_service import SchedulingService
from app.dao.order_dao import OrderDAO
from app.models.vehicle import Vehicle
from app.simulation.clock import clock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/piles", tags=["充电桩管理"])


@router.get("", response_model=list[PileResponse])
async def list_piles(
    current_user: dict = Depends(get_current_user),
    svc: PileService = Depends(get_pile_service),
):
    piles = await svc.get_all_piles()
    return piles


@router.get("/{pile_id}", response_model=PileWithVehicles)
async def get_pile(
    pile_id: int,
    current_user: dict = Depends(get_current_user),
    svc: PileService = Depends(get_pile_service),
    sched_svc: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db),
):
    pile = await svc.get_pile(pile_id)
    if not pile:
        raise HTTPException(status_code=404, detail="充电桩不存在")

    entries = await sched_svc.queue_dao.get_pile_queue_entries(pile_id)
    vehicles = []
    for e in entries:
        order = await sched_svc.order_dao.get_by_id(e.order_id)
        if not order:
            continue
        # 查询车辆信息
        vehicle = None
        if order.vehicle_id:
            result = await db.execute(select(Vehicle).where(Vehicle.id == order.vehicle_id))
            vehicle = result.scalar_one_or_none()

        vehicles.append({
            "order_id": e.order_id,
            "user_id": order.user_id,
            "queue_number": order.queue_number or "",
            "requested_kwh": order.requested_kwh,
            "battery_capacity": vehicle.battery_capacity if vehicle else 0,
            "is_charging": e.is_charging,
            "position": e.position,
            "entered_at": e.entered_at.isoformat() if e.entered_at else None,
            "queue_duration_minutes": round(
                (clock.now - e.entered_at).total_seconds() / 60, 2
            ) if e.entered_at else 0,
        })

    return PileWithVehicles(
        id=pile.id, pile_code=pile.pile_code, mode=pile.mode,
        power_rate=pile.power_rate, status=pile.status.value if hasattr(pile.status, 'value') else pile.status,
        total_charge_count=pile.total_charge_count,
        total_charge_duration=pile.total_charge_duration,
        total_charge_kwh=pile.total_charge_kwh,
        queue_vehicles=vehicles
    )


@router.post("/{pile_id}/start", response_model=MessageResponse)
async def start_pile(
    pile_id: int,
    current_user: dict = Depends(get_current_admin),
    svc: PileService = Depends(get_pile_service),
):
    try:
        await svc.start_pile(pile_id)
        return MessageResponse(message="充电桩已启动")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{pile_id}/stop", response_model=MessageResponse)
async def stop_pile(
    pile_id: int,
    current_user: dict = Depends(get_current_admin),
    svc: PileService = Depends(get_pile_service),
):
    try:
        await svc.stop_pile(pile_id)
        return MessageResponse(message="充电桩已停止")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
