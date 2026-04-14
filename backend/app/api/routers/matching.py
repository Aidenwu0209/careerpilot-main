from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_user, get_db_session
from app.api.routers.students import resolve_target_job
from app.models import MatchResult, Student, User
from app.schemas.matching import MatchingRequest, MatchingResponse
from app.services.bootstrap import ServiceContainer

router = APIRouter()


@router.post("/analyze", response_model=MatchingResponse)
def analyze_matching(
    payload: MatchingRequest,
    current_user: User = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
    db: Session = Depends(get_db_session),
) -> MatchingResponse:
    # Verify user has access
    if current_user.role not in ["student", "admin", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

    job_code = payload.job_code
    if not job_code:
        student = db.scalar(select(Student).where(Student.user_id == current_user.id))
        if student:
            job_code, _ = resolve_target_job(db, student)
    if not job_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法确定目标岗位，请先选择或确认一个目标岗位")

    try:
        result = container.matching_service.analyze_match(db, payload.student_id, job_code)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MatchingResponse(**result)


@router.get("/{match_id}", response_model=MatchingResponse)
def get_match_result(
    match_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> MatchingResponse:
    """获取指定的匹配结果历史记录"""
    match_result = db.scalar(
        select(MatchResult).where(MatchResult.id == match_id)
    )
    if not match_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="匹配记录不存在")

    # 验证用户权限
    student_profile = match_result.student_profile
    if not student_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生画像不存在")

    student = student_profile.student
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生信息不存在")

    # 检查权限：只有学生本人、教师和管理员可以查看
    if current_user.role == "student" and student.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此记录")

    if current_user.role not in ["student", "admin", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

    return MatchingResponse(
        student_profile_id=match_result.student_profile_id,
        job_profile_id=match_result.job_profile_id,
        total_score=match_result.total_score,
        dimensions=match_result.dimensions_json or [],
        gap_items=match_result.gap_items_json or [],
        summary=match_result.summary or "",
    )

