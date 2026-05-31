from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.dependencies import get_db, get_current_user, get_current_admin
from app.models.vehicle import Vehicle
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/vehicles", tags=["车辆管理"])


class VehicleCreate(BaseModel):
    license_plate: str = Field(..., min_length=1, max_length=20)
    battery_capacity: float = Field(..., gt=0)


class VehicleResponse(BaseModel):
    id: int
    user_id: int
    license_plate: str
    battery_capacity: float

    model_config = {"from_attributes": True}


@router.post("", response_model=VehicleResponse)
async def create_vehicle(
    req: VehicleCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    v = Vehicle(
        user_id=int(current_user["sub"]),
        license_plate=req.license_plate,
        battery_capacity=req.battery_capacity,
    )
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


@router.get("", response_model=list[VehicleResponse])
async def list_my_vehicles(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vehicle).where(Vehicle.user_id == int(current_user["sub"]))
    )
    return result.scalars().all()


@router.get("/all", response_model=list[VehicleResponse])
async def list_all_vehicles(
    current_user: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle))
    return result.scalars().all()
