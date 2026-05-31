from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import (
    get_fault_service, get_scheduling_service, get_current_user, get_current_admin
)
from app.schemas import FaultReportRequest, FaultRescheduleRequest, FaultResponse, MessageResponse
from app.services.fault_service import FaultService
from app.services.scheduling_service import SchedulingService

router = APIRouter(prefix="/api/v1/faults", tags=["故障管理"])


@router.post("/{pile_id}", response_model=MessageResponse)
async def report_fault(
    pile_id: int,
    req: FaultReportRequest,
    current_user: dict = Depends(get_current_admin),
    fault_svc: FaultService = Depends(get_fault_service),
    sched_svc: SchedulingService = Depends(get_scheduling_service),
):
    record = await fault_svc.report_fault(pile_id, int(current_user["sub"]), req.strategy)
    result = await sched_svc.handle_fault(pile_id, req.strategy)
    record.affected_order_count = result["affected_count"]
    return MessageResponse(
        message=f"故障已上报，使用{req.strategy}策略，影响{result['affected_count']}个订单",
        detail=result
    )


@router.post("/{pile_id}/reschedule", response_model=MessageResponse)
async def reschedule(
    pile_id: int,
    req: FaultRescheduleRequest,
    current_user: dict = Depends(get_current_admin),
    sched_svc: SchedulingService = Depends(get_scheduling_service),
):
    result = await sched_svc.handle_fault(pile_id, req.strategy)
    return MessageResponse(
        message=f"重调度完成，策略：{req.strategy}",
        detail=result
    )


@router.post("/{pile_id}/recover", response_model=MessageResponse)
async def recover_pile(
    pile_id: int,
    current_user: dict = Depends(get_current_admin),
    sched_svc: SchedulingService = Depends(get_scheduling_service),
    fault_svc: FaultService = Depends(get_fault_service),
):
    result = await sched_svc.handle_fault_recovery(pile_id)
    faults = await fault_svc.get_active_faults()
    for f in faults:
        if f.pile_id == pile_id:
            await fault_svc.resolve_fault(f.id)
    return MessageResponse(
        message=f"充电桩已恢复，重新分配{result['redistributed']}个订单",
        detail=result
    )


@router.get("", response_model=list[FaultResponse])
async def list_faults(
    current_user: dict = Depends(get_current_user),
    svc: FaultService = Depends(get_fault_service),
):
    return await svc.get_all_faults()
