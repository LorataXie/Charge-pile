from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_scheduling_service, get_billing_service, get_db, get_current_user
from app.schemas import (
    ChargeRequest, ModifyChargeRequest, ChargeOrderResponse,
    BillingDetailResponse, MessageResponse
)
from app.services.scheduling_service import SchedulingService
from app.services.billing_service import BillingService
from app.dao.order_dao import OrderDAO
from app.dao.vehicle_dao import VehicleDAO
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orders", tags=["充电请求"])


async def _own_order(order_id: int, user_id: int, db: AsyncSession):
    """校验订单归属，不通过则 403。"""
    dao = OrderDAO(db)
    order = await dao.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此订单")
    return order


async def _own_vehicle(vehicle_id: int, user_id: int, db: AsyncSession):
    """校验车辆归属，不通过则 403。"""
    dao = VehicleDAO(db)
    v = await dao.get_by_id(vehicle_id)
    if not v:
        raise HTTPException(status_code=404, detail="车辆不存在")
    if v.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权使用此车辆")
    return v


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
    return await _own_order(order_id, int(current_user["sub"]), db)


@router.post("", response_model=ChargeOrderResponse)
async def submit_order(
    req: ChargeRequest,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db),
):
    uid = int(current_user["sub"])
    await _own_vehicle(req.vehicle_id, uid, db)
    try:
        return await svc.submit_request(uid, req.vehicle_id, req.mode, req.requested_kwh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{order_id}", response_model=ChargeOrderResponse)
async def modify_order(
    order_id: int,
    req: ModifyChargeRequest,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db),
):
    await _own_order(order_id, int(current_user["sub"]), db)
    try:
        return await svc.modify_request(order_id, req.new_mode, req.new_kwh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{order_id}", response_model=ChargeOrderResponse)
async def cancel_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db),
):
    await _own_order(order_id, int(current_user["sub"]), db)
    try:
        return await svc.cancel_request(order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/end", response_model=ChargeOrderResponse)
async def end_charging(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    svc: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db),
):
    await _own_order(order_id, int(current_user["sub"]), db)
    try:
        return await svc.end_charging(order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{order_id}/detail", response_model=BillingDetailResponse)
async def get_detail(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    billing_svc: BillingService = Depends(get_billing_service),
    db: AsyncSession = Depends(get_db),
):
    # 详单必须本人才能看
    await _own_order(order_id, int(current_user["sub"]), db)
    detail = await billing_svc.get_detail(order_id)
    if not detail:
        raise HTTPException(status_code=404, detail="详单不存在")
    return detail
