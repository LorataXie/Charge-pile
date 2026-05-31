from datetime import datetime
from fastapi import APIRouter, Depends
from app.dependencies import get_db, get_current_user, get_current_admin
from app.simulation.clock import clock
from app.simulation.engine import SimulationEngine
from app.schemas import SimTimeResponse, MessageResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/sim", tags=["仿真控制"])


@router.get("/clock", response_model=SimTimeResponse)
async def get_clock(current_user: dict = Depends(get_current_user)):
    return clock.to_dict()


@router.post("/tick", response_model=MessageResponse)
async def tick(
    current_user: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    engine = SimulationEngine(db)
    result = await engine.tick()
    return MessageResponse(message="Tick completed", detail=result)


@router.post("/clock/set", response_model=SimTimeResponse)
async def set_clock(
    dt: str,
    current_user: dict = Depends(get_current_admin),
):
    clock.set(datetime.fromisoformat(dt))
    return clock.to_dict()
