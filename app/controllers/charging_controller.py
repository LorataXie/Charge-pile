from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_scheduling_service, get_billing_service, get_db, get_current_user
from app.schemas import (
    ChargeRequest, ModifyChargeRequest, ChargeOrderResponse,
    BillingDetailResponse, MessageResponse
)
from app.services.scheduling_service import SchedulingService
from app.services.billing_service import BillingService
from app.dao.order_dao import OrderDAO
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orders", tags=["充电请求"])


@router.get("", response_model=list[ChargeOrderResponse])
async def list_my_orders(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dao = OrderDAO(db)
    orders = await dao.get_by_user_id(int(current_user["sub"]))
    return sorted(orders, key=lambda o: o.id, reverse=True)


@router.get("/{order_id}", response_model=ChargeOrderResponse)
async def get_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dao = OrderDAO(db)
    order = await dao.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


@router.post("", response_model=ChargeOrderResponse)
async def submit_order(
    req: ChargeRequest,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
):
    try:
        order = await svc.submit_request(
            user_id=int(current_user["sub"]),
            vehicle_id=req.vehicle_id,
            mode=req.mode,
            requested_kwh=req.requested_kwh,
        )
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{order_id}", response_model=ChargeOrderResponse)
async def modify_order(
    order_id: int,
    req: ModifyChargeRequest,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
):
    try:
        order = await svc.modify_request(
            order_id=order_id,
            new_mode=req.new_mode,
            new_kwh=req.new_kwh,
        )
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{order_id}", response_model=ChargeOrderResponse)
async def cancel_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
):
    try:
        order = await svc.cancel_request(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/end", response_model=ChargeOrderResponse)
async def end_charging(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
):
    try:
        order = await svc.end_charging(order_id)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{order_id}/detail", response_model=BillingDetailResponse)
async def get_detail(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    billing_svc: BillingService = Depends(get_billing_service),
):
    detail = await billing_svc.get_detail(order_id)
    if not detail:
        raise HTTPException(status_code=404, detail="详单不存在")
    return detail
