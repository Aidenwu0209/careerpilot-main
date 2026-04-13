from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.deps import get_current_user, get_db_session
from app.models import (
    CareerReport,
    ChatMessageRecord,
    HistoryTitle,
    JobProfile,
    JobPosting,
    MatchResult,
    PathRecommendation,
    Student,
    StudentProfile,
    User,
)
from app.services.matching.recommendation import (
    extract_resume_experience_context,
    score_recommended_job,
)
from app.services.student import resolve_target_job

router = APIRouter()


@router.get("/me")
def get_current_student(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    student = db.scalar(select(Student).where(Student.user_id == current_user.id))
    if not student:
        return {
            "student_id": None,
            "user_id": current_user.id,
            "major": "",
            "grade": "",
            "career_goal": "",
            "confirmed_job_code": None,
            "confirmed_job_title": None,
            "suggested_job_code": None,
            "suggested_job_title": None,
        }

    suggested_job_code, suggested_job_title = resolve_target_job(student, db)

    return {
        "student_id": student.id,
        "user_id": current_user.id,
        "major": student.major,
        "grade": student.grade,
        "career_goal": student.career_goal,
        "confirmed_job_code": student.confirmed_job_code,
        "confirmed_job_title": student.confirmed_job_title,
        "suggested_job_code": suggested_job_code,
        "suggested_job_title": suggested_job_title,
    }


class SetTargetJobRequest(BaseModel):
    job_code: str = Field(..., min_length=1, max_length=80)
    job_title: str = Field(..., min_length=1, max_length=120)


@router.patch("/me/target-job")
def set_target_job(
    payload: SetTargetJobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    student = db.scalar(select(Student).where(Student.user_id == current_user.id))
    if not student:
        return {"ok": False, "error": "学生档案不存在"}
    student.confirmed_job_code = payload.job_code
    student.confirmed_job_title = payload.job_title
    db.commit()
    return {"ok": True, "confirmed_job_code": payload.job_code, "confirmed_job_title": payload.job_title}


@router.get("/me/recommended-jobs")
def get_recommended_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    student = db.scalar(select(Student).where(Student.user_id == current_user.id))
    if not student:
        return {"items": []}

    student_profile = db.scalar(
        select(StudentProfile).where(StudentProfile.student_id == student.id)
    )

    jobs = []

    all_profiles = list(db.scalars(select(JobProfile)).all())
    postings = {
        item.job_code: item
        for item in db.scalars(select(JobPosting)).all()
    }
    experience = extract_resume_experience_context(db, current_user.id, source_summary=student_profile.source_summary if student_profile else "")
    max_recommended = 30
    min_score = 60.0

    if student_profile:
        scored_profiles = []

        for jp in all_profiles:
            posting = postings.get(jp.job_code)
            scoring = score_recommended_job(student_profile, jp, experience, posting)
            final_score = scoring["score"]
            if final_score < min_score:
                continue
            scored_profiles.append((final_score, scoring, jp, posting))

        scored_profiles.sort(key=lambda item: item[0], reverse=True)
        diversified_profiles = []
        title_counts: dict[str, int] = {}
        max_per_title = 6
        for item in scored_profiles:
            title = item[2].title
            if title_counts.get(title, 0) >= max_per_title:
                continue
            diversified_profiles.append(item)
            title_counts[title] = title_counts.get(title, 0) + 1
            if len(diversified_profiles) >= max_recommended:
                break

        logger.info(
            "推荐岗位统计: 总岗位数=%s, 60分以上岗位数=%s, 多样化后=%s, 项目数=%s, 实习数=%s, 将返回=%s",
            len(all_profiles),
            len(scored_profiles),
            len(diversified_profiles),
            experience["project_count"],
            experience["internship_count"],
            min(len(diversified_profiles), max_recommended),
        )

        for _, scoring, jp, posting in diversified_profiles:
            company_name = posting.company_name if posting else "推荐岗位"
            salary_range = posting.salary_range if posting and posting.salary_range else ""
            skills = jp.skill_requirements[:5] if jp.skill_requirements else []
            matched = list(dict.fromkeys(scoring["matched_skills"] + scoring["experience_tags"] + scoring["intent_tags"]))[:6]
            missing = scoring["missing_skills"][:4]

            # Build evidence-based reason — always cite concrete evidence
            evidence_parts: list[str] = []
            if scoring["matched_certificates"]:
                evidence_parts.append(f"持有 {', '.join(scoring['matched_certificates'][:3])}")
            if scoring["experience_reason"]:
                evidence_parts.append(scoring["experience_reason"])
            if matched:
                evidence_parts.append(f"已掌握 {', '.join(matched[:4])}")

            if scoring["intent_tags"]:
                reason = f"OCR 意向岗位命中 {', '.join(scoring['intent_tags'])}；{'；'.join(evidence_parts)}"
            elif evidence_parts:
                reason = "；".join(evidence_parts) + ("。" if not evidence_parts[0].endswith("。") else "")
            elif missing:
                reason = f"当前缺少 {', '.join(missing[:3])}，建议优先补齐。"
            else:
                reason = "基础画像符合岗位最低门槛。"

            jobs.append({
                "job_code": jp.job_code,
                "title": jp.title,
                "company": company_name,
                "salary": salary_range,
                "location": posting.location if posting else "",
                "industry": posting.industry if posting else "",
                "company_size": posting.company_size if posting else "",
                "ownership_type": posting.ownership_type if posting else "",
                "summary": jp.summary or (posting.description if posting else ""),
                "tags": skills,
                "matched_tags": matched,
                "missing_tags": missing,
                "matched_certificates": scoring["matched_certificates"],
                "missing_certificates": scoring["missing_certificates"],
                "experience_tags": scoring["experience_tags"],
                "intent_tags": scoring["intent_tags"],
                "reason": reason,
                "match_score": scoring["score"],
                "base_score": scoring["base_score"],
                "experience_score": scoring["experience_score"],
                "skill_score": scoring["skill_score"],
                "potential_score": scoring["potential_score"],
            })

    return {"items": jobs}


@router.get("/me/history")
def get_student_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    student = db.scalar(select(Student).where(Student.user_id == current_user.id))
    if not student:
        return {"items": []}

    records = []

    reports = list(db.scalars(
        select(CareerReport)
        .where(CareerReport.student_id == student.id)
        .order_by(CareerReport.created_at.desc())
        .limit(20)
    ).all())

    for r in reports:
        jp = db.scalar(
            select(JobProfile).where(JobProfile.job_code == r.target_job_code).limit(1)
        )
        title = f"职业规划报告 — {jp.title}" if jp else f"职业规划报告 — {r.target_job_code}"
        desc = f"报告状态: {r.status}"
        if r.status == "completed":
            desc = "已完成职业规划报告"
        elif r.status == "edited":
            desc = "已编辑职业规划报告"

        records.append({
            "id": f"report-{r.id}",
            "type": "report",
            "ref_id": r.id,
            "title": title,
            "desc": desc,
            "time": r.created_at.isoformat() if r.created_at else "",
        })

    student_profile = db.scalar(
        select(StudentProfile).where(StudentProfile.student_id == student.id)
    )
    if student_profile:
        matches = list(db.scalars(
            select(MatchResult)
            .where(MatchResult.student_profile_id == student_profile.id)
            .order_by(MatchResult.created_at.desc())
            .limit(20)
        ).all())

        for m in matches:
            jp = db.scalar(
                select(JobProfile).where(JobProfile.id == m.job_profile_id).limit(1)
            )
            title = f"岗位匹配 — {jp.title}" if jp else "岗位匹配"
            desc = f"匹配度 {round(m.total_score, 1)}"

            records.append({
                "id": f"match-{m.id}",
                "type": "matching",
                "ref_id": m.id,
                "title": title,
                "desc": desc,
                "time": m.created_at.isoformat() if m.created_at else "",
            })

    paths = list(db.scalars(
        select(PathRecommendation)
        .where(PathRecommendation.student_id == student.id)
        .order_by(PathRecommendation.created_at.desc())
        .limit(10)
    ).all())

    for p in paths:
        jp = db.scalar(
            select(JobProfile).where(JobProfile.job_code == p.target_job_code).limit(1)
        )
        title = f"职业路径规划 — {jp.title}" if jp else f"职业路径规划 — {p.target_job_code}"

        records.append({
            "id": f"path-{p.id}",
            "type": "path",
            "ref_id": p.id,
            "title": title,
            "desc": "已生成职业发展路径",
            "time": p.created_at.isoformat() if p.created_at else "",
        })

    chat_msgs = list(db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.user_id == current_user.id, ChatMessageRecord.role == "user")
        .order_by(ChatMessageRecord.created_at.desc())
        .limit(30)
    ).all())

    for msg in chat_msgs:
        summary = msg.content[:50] + ("..." if len(msg.content) > 50 else "")
        records.append({
            "id": f"chat-{msg.id}",
            "type": "chat",
            "ref_id": msg.id,
            "title": f"AI 对话 — {summary}",
            "desc": "AI 职业规划咨询" + ("（含简历上下文）" if msg.has_context else ""),
            "time": msg.created_at.isoformat() if msg.created_at else "",
        })

    records.sort(key=lambda x: x["time"], reverse=True)

    custom_titles = db.scalars(
        select(HistoryTitle).where(HistoryTitle.user_id == current_user.id)
    ).all()
    title_map = {f"{ct.record_type}-{ct.ref_id}": ct.custom_title for ct in custom_titles}

    for rec in records:
        key = f"{rec['type']}-{rec['ref_id']}"
        if key in title_map and title_map[key]:
            rec["title"] = title_map[key]

    return {"items": records[:30]}


class RenameHistoryRequest(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=40)
    ref_id: int = Field(..., gt=0)
    custom_title: str = Field(..., min_length=1, max_length=200)


@router.patch("/me/history/rename")
def rename_history_item(
    payload: RenameHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    existing = db.scalar(
        select(HistoryTitle).where(
            HistoryTitle.user_id == current_user.id,
            HistoryTitle.record_type == payload.record_type,
            HistoryTitle.ref_id == payload.ref_id,
        )
    )
    if existing:
        existing.custom_title = payload.custom_title
    else:
        db.add(HistoryTitle(
            user_id=current_user.id,
            record_type=payload.record_type,
            ref_id=payload.ref_id,
            custom_title=payload.custom_title,
        ))
    db.commit()
    return {"ok": True}
