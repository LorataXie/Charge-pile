from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_scheduling_service, get_db, get_current_user
from app.schemas import QueueStatusResponse
from app.services.scheduling_service import SchedulingService
from app.dao.queue_dao import QueueDAO
from app.dao.order_dao import OrderDAO
from app.models.user import User
from app.simulation.clock import clock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/queue", tags=["排队状态"])


@router.get("/status/{order_id}", response_model=QueueStatusResponse)
async def get_queue_status(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
):
    try:
        return await svc.get_queue_status(order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/waiting-area")
async def get_waiting_area(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dao = QueueDAO(db)
    order_dao = OrderDAO(db)
    entries = await dao.get_all_waiting_entries()
    result = []
    for e in entries:
        order = await order_dao.get_by_id(e.order_id)
        username = None
        if order:
            user_result = await db.execute(select(User).where(User.id == order.user_id))
            user = user_result.scalar_one_or_none()
            username = user.username if user else None
        result.append({
            "order_id": e.order_id,
            "queue_number": e.queue_number,
            "mode": e.mode,
            "user_id": order.user_id if order else None,
            "username": username,
            "requested_kwh": order.requested_kwh if order else 0,
            "position": e.position,
            "is_paused": e.is_paused,
            "entered_at": e.entered_at.isoformat() if e.entered_at else None,
            "queue_duration_minutes": round(
                (clock.now - e.entered_at).total_seconds() / 60, 2
            ) if e.entered_at else 0,
        })
    return result
