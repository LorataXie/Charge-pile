from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_scheduling_service, get_db, get_current_user
from app.schemas import QueueStatusResponse
from app.services.scheduling_service import SchedulingService
from app.dao.queue_dao import QueueDAO
from sqlalchemy.ext.asyncio import AsyncSession

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
    entries = await dao.get_all_waiting_entries()
    return [
        {
            "order_id": e.order_id,
            "queue_number": e.queue_number,
            "mode": e.mode,
            "position": e.position,
            "is_paused": e.is_paused,
            "entered_at": e.entered_at.isoformat() if e.entered_at else None,
        }
        for e in entries
    ]
