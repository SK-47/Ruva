from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional

from app.services.report_service import ReportService
from app.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


def get_report_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ReportService:
    """Dependency to get report service"""
    return ReportService(db)


@router.post("/session/{session_id}/participant/{participant_id}")
async def generate_participant_report(
    session_id: str,
    participant_id: str,
    service: ReportService = Depends(get_report_service)
):
    """Generate comprehensive performance report for a participant"""
    try:
        report = await service.generate_participant_report(session_id, participant_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.post("/session/{session_id}")
async def generate_session_report(
    session_id: str,
    service: ReportService = Depends(get_report_service)
):
    """Generate comprehensive report for entire session (all participants)"""
    try:
        report = await service.generate_session_report(session_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate session report: {str(e)}")


@router.get("/participant/{participant_id}/history")
async def get_participant_history(
    participant_id: str,
    limit: int = Query(10, ge=1, le=100),
    service: ReportService = Depends(get_report_service)
):
    """Get session history for a participant with summary metrics"""
    try:
        history = await service.get_participant_history(participant_id, limit)
        return {
            "participant_id": participant_id,
            "total_sessions": len(history),
            "sessions": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve history: {str(e)}")


@router.get("/export/{report_id}")
async def export_report(
    report_id: str,
    format: str = Query("json", regex="^(json|pdf-ready)$"),
    service: ReportService = Depends(get_report_service)
):
    """Export a report in specified format (json or pdf-ready)"""
    try:
        exported_report = await service.export_report(report_id, format)
        return exported_report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export report: {str(e)}")


@router.get("/session/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    service: ReportService = Depends(get_report_service)
):
    """Get quick summary of session performance"""
    try:
        # Check if full report exists
        db = service.db
        session_report = await db.session_reports.find_one({"session_info.session_id": session_id})
        
        if session_report:
            # Return summary from existing report
            return {
                "session_id": session_id,
                "statistics": session_report.get("session_statistics", {}),
                "generated_at": session_report.get("generated_at")
            }
        else:
            # Generate new report
            report = await service.generate_session_report(session_id)
            return {
                "session_id": session_id,
                "statistics": report.get("session_statistics", {}),
                "generated_at": report.get("generated_at")
            }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session summary: {str(e)}")
