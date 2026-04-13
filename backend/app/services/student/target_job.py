from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import JobProfile, MatchResult, Student, StudentProfile


def resolve_target_job(student: Student, db: Session) -> tuple[Optional[str], Optional[str]]:
    """Unified target job resolution with priority order:

    1. User manually confirmed job (confirmed_job_code)
    2. Most recent match result
    3. Career goal fuzzy match against JobProfile
    4. Return None (no fallback to first recommended job on backend)
    """
    # Priority 1: User manually confirmed job
    if student.confirmed_job_code:
        return student.confirmed_job_code, student.confirmed_job_title

    # Priority 2: Most recent match result
    student_profile = db.scalar(
        select(StudentProfile).where(StudentProfile.student_id == student.id)
    )
    if student_profile:
        latest_match = db.scalar(
            select(MatchResult)
            .where(MatchResult.student_profile_id == student_profile.id)
            .order_by(MatchResult.created_at.desc())
            .limit(1)
        )
        if latest_match:
            jp = db.scalar(
                select(JobProfile).where(JobProfile.id == latest_match.job_profile_id).limit(1)
            )
            if jp:
                return jp.job_code, jp.title

    # Priority 3: Career goal fuzzy match
    if student.career_goal:
        jp = db.scalar(
            select(JobProfile)
            .where(func.lower(JobProfile.title).contains(student.career_goal.lower()))
            .limit(1)
        )
        if jp:
            return jp.job_code, jp.title

    return None, None
