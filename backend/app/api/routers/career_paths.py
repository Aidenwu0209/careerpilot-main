from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_user, get_db_session
from app.models import PathRecommendation, Student, StudentProfile, User
from app.schemas.common import APIResponse
from app.schemas.matching import MatchingRequest
from app.services.bootstrap import ServiceContainer

router = APIRouter()


@router.post("/plan", response_model=APIResponse)
async def plan_career_path(
    payload: MatchingRequest,
    current_user: User = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
    db: Session = Depends(get_db_session),
) -> APIResponse:
    # Verify user has access
    if current_user.role not in ["student", "admin", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

    result = await container.career_path_service.plan_path(db, payload.student_id, payload.job_code)
    return APIResponse(data=result)


@router.get("/{path_id}", response_model=APIResponse)
def get_path_result(
    path_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> APIResponse:
    """获取指定的路径规划历史记录"""
    path_result = db.scalar(
        select(PathRecommendation).where(PathRecommendation.id == path_id)
    )
    if not path_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="路径规划记录不存在")

    # 检查权限：只有学生本人、教师和管理员可以查看
    student = db.scalar(select(Student).where(Student.id == path_result.student_id))
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生信息不存在")

    if current_user.role == "student" and student.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此记录")

    if current_user.role not in ["student", "admin", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

    # 兼容旧记录：vertical_graph_json/transition_graph_json 为空 dict 时降级
    vertical_graph = path_result.vertical_graph_json if path_result.vertical_graph_json else {}
    transition_graph = path_result.transition_graph_json if path_result.transition_graph_json else {}

    return APIResponse(data={
        "primary_path": path_result.primary_path_json or [],
        "alternate_paths": path_result.alternate_paths_json or [],
        "vertical_graph": vertical_graph,
        "transition_graph": transition_graph,
        "gaps": path_result.gaps_json or [],
        "recommendations": path_result.recommendations_json or [],
        "rationale": path_result.rationale or "历史记录仅保留基础路径；重新生成可查看完整岗位图谱。",
        "target_job_code": path_result.target_job_code,
    })
