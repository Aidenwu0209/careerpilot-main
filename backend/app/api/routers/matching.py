from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_user, get_db_session
from app.models import MatchDimensionScore, MatchResult, User
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

    result = container.matching_service.analyze_match(db, payload.student_id, payload.job_code)
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

    # Build dimensions list from stored JSON (new records) or MatchDimensionScore table (old records)
    dimensions = match_result.dimensions_json if match_result.dimensions_json else []
    if not dimensions:
        # Backward compatibility: reconstruct from MatchDimensionScore table
        dim_scores = list(db.scalars(
            select(MatchDimensionScore)
            .where(MatchDimensionScore.match_result_id == match_result.id)
        ).all())
        dimensions = [
            {
                "dimension": ds.dimension,
                "score": ds.score,
                "weight": ds.weight,
                "reasoning": ds.reasoning,
                "evidence": ds.evidence_json or {},
            }
            for ds in dim_scores
        ]

    student_id = student_profile.student_id if student_profile else 0

    # Use stored job_code or derive from job_profile relationship
    job_code = match_result.job_code or ""
    if not job_code and match_result.job_profile:
        job_code = match_result.job_profile.job_code

    # Use stored weights or derive default
    weights = match_result.weights_json if match_result.weights_json else {
        "basic_requirements": 0.2,
        "professional_skills": 0.4,
        "professional_literacy": 0.2,
        "development_potential": 0.2,
    }

    return MatchingResponse(
        student_id=student_id,
        job_code=job_code,
        total_score=match_result.total_score,
        weights=weights,
        dimensions=dimensions,
        gap_items=match_result.gaps_json or [],
        suggestions=match_result.suggestions_json or [],
        summary=match_result.summary or "",
    )

