from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_report_service, get_current_user, get_current_admin
from app.schemas import ReportGenerateRequest, ReportResponse, MessageResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["报表"])


@router.post("", response_model=ReportResponse)
async def generate_report(
    req: ReportGenerateRequest,
    current_user: dict = Depends(get_current_admin),
    svc: ReportService = Depends(get_report_service),
):
    return await svc.generate_report(req.report_type, req.period_start)


@router.get("", response_model=list[ReportResponse])
async def list_reports(
    current_user: dict = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    return await svc.get_reports()


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    current_user: dict = Depends(get_current_user),
    svc: ReportService = Depends(get_report_service),
):
    report = await svc.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报表不存在")
    return report
