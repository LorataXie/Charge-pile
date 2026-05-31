from fastapi import APIRouter, Depends
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/billing", tags=["计费"])


@router.get("/rules")
async def get_rules(current_user: dict = Depends(get_current_user)):
    return {
        "pricing": [
            {"period": "PEAK", "price_per_kwh": 1.0, "hours": "10:00-15:00, 18:00-21:00"},
            {"period": "NORMAL", "price_per_kwh": 0.7, "hours": "7:00-10:00, 15:00-18:00, 21:00-23:00"},
            {"period": "VALLEY", "price_per_kwh": 0.4, "hours": "23:00-次日7:00"},
        ],
        "service_fee_per_kwh": 0.8,
        "formula": "总费用 = 充电费(∑时段电量×时段电价) + 服务费(总电量×0.8)"
    }
