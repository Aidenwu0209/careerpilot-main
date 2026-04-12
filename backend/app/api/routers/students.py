from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
    UploadedFile,
    User,
)
from app.services.matching.scoring import (
    score_basic_requirements,
    score_development_potential,
    score_professional_literacy,
    score_professional_skills,
)

router = APIRouter()


EXPERIENCE_KEYWORDS = [
    "AI", "算法", "机器学习", "深度学习", "PyTorch", "TensorFlow", "模型", "建模", "数据",
    "分析", "SQL", "Python", "Java", "JavaScript", "TypeScript", "React", "Vue",
    "前端", "后端", "接口", "API", "FastAPI", "测试", "自动化", "运维", "Linux",
    "产品", "需求", "原型", "可视化", "统计", "项目", "实习",
]


def _safe_list(value: object) -> list[str]:
    return [str(item).strip() for item in value or [] if str(item).strip()]


def _extract_resume_experience_context(db: Session, owner_id: int) -> dict:
    files = list(db.scalars(
        select(UploadedFile)
        .where(UploadedFile.owner_id == owner_id)
        .order_by(UploadedFile.created_at.desc())
        .limit(8)
    ).all())
    projects: list[str] = []
    internships: list[str] = []
    raw_sections: list[str] = []
    section_markers = ("项目经历", "项目经验", "项目实践", "实习经历", "实习经验", "工作经历", "实践经历")

    for file in files:
        ocr = (file.meta_json or {}).get("ocr") if file.meta_json else None
        if not ocr:
            continue
        structured = ocr.get("structured_json") or {}
        projects.extend(_safe_list(structured.get("projects")))
        internships.extend(_safe_list(structured.get("internships")))

        lines = [line.strip() for line in str(ocr.get("raw_text") or "").splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            if any(marker in line for marker in section_markers):
                raw_sections.extend(lines[idx: idx + 10])

    project_text = "；".join(dict.fromkeys(projects + raw_sections))
    internship_text = "；".join(dict.fromkeys(internships))
    combined = f"{project_text}；{internship_text}".strip("；")
    return {
        "text": combined,
        "projects": projects,
        "internships": internships,
        "project_count": len([item for item in projects if len(item) > 2]),
        "internship_count": len([item for item in internships if len(item) > 2]),
    }


def _score_experience_context(experience: dict, job_profile: JobProfile, posting: JobPosting | None) -> dict:
    text = str(experience.get("text") or "")
    if not text:
        return {"score": 0.0, "tags": [], "reason": ""}

    lowered_text = text.lower()
    required_skills = _safe_list(job_profile.skill_requirements)
    matched_skills = [
        skill for skill in required_skills
        if skill.lower() in lowered_text or skill.replace(" ", "").lower() in lowered_text.replace(" ", "")
    ]
    job_blob = " ".join([
        job_profile.title or "",
        job_profile.summary or "",
        " ".join(required_skills),
        posting.description if posting else "",
    ]).lower()
    matched_topics = [
        keyword for keyword in EXPERIENCE_KEYWORDS
        if keyword.lower() in lowered_text and keyword.lower() in job_blob
    ]
    score = 0.0
    if required_skills:
        score += min(70.0, len(matched_skills) / max(1, len(required_skills)) * 70)
    score += min(25.0, len(matched_topics) * 5)
    if experience.get("project_count", 0) > 0:
        score += 6
    if experience.get("internship_count", 0) > 0:
        score += 4

    tags = list(dict.fromkeys(matched_skills + matched_topics))[:6]
    reason = ""
    if tags:
        reason = f"项目/实习经历中匹配到 {', '.join(tags[:4])}。"
    return {"score": round(min(100.0, score), 1), "tags": tags, "reason": reason}


def _score_recommended_job(student_profile: StudentProfile, job_profile: JobProfile, experience: dict | None = None, posting: JobPosting | None = None) -> dict:
    student_data = {
        "skills": student_profile.skills_json or [],
        "certificates": student_profile.certificates_json or [],
        "capability_scores": student_profile.capability_scores or {},
        "completeness_score": student_profile.completeness_score or 0,
        "competitiveness_score": student_profile.competitiveness_score or 0,
    }
    job_data = {
        "title": job_profile.title,
        "skill_requirements": job_profile.skill_requirements or [],
        "certificate_requirements": job_profile.certificate_requirements or [],
        "capability_scores": job_profile.capability_scores or {},
    }
    weights = job_profile.dimension_weights or {
        "basic_requirements": 0.2,
        "professional_skills": 0.4,
        "professional_literacy": 0.2,
        "development_potential": 0.2,
    }
    basic_score, basic_evidence = score_basic_requirements(student_data, job_data)
    skill_score, skill_evidence = score_professional_skills(student_data, job_data)
    literacy_score, _ = score_professional_literacy(student_data, job_data)
    potential_score, _ = score_development_potential(student_data, job_data)
    total_score = round(
        basic_score * weights.get("basic_requirements", 0.2)
        + skill_score * weights.get("professional_skills", 0.4)
        + literacy_score * weights.get("professional_literacy", 0.2)
        + potential_score * weights.get("development_potential", 0.2),
        1,
    )
    experience_result = _score_experience_context(experience or {}, job_profile, posting)
    adjusted_score = round(
        min(100.0, total_score + experience_result["score"] * 0.28),
        1,
    )
    return {
        "score": adjusted_score,
        "base_score": total_score,
        "experience_score": experience_result["score"],
        "experience_tags": experience_result["tags"],
        "experience_reason": experience_result["reason"],
        "matched_skills": skill_evidence.get("matched_skills", []),
        "missing_skills": skill_evidence.get("missing_skills", []),
        "matched_certificates": basic_evidence.get("matched_certificates", []),
        "skill_score": round(skill_score, 1),
        "potential_score": round(potential_score, 1),
    }


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
            "suggested_job_code": None,
            "suggested_job_title": None,
        }

    suggested_job_code = None
    suggested_job_title = None
    if student.career_goal:
        jp = db.scalar(
            select(JobProfile)
            .where(func.lower(JobProfile.title).contains(student.career_goal.lower()))
            .limit(1)
        )
        if jp:
            suggested_job_code = jp.job_code
            suggested_job_title = jp.title

    return {
        "student_id": student.id,
        "user_id": current_user.id,
        "major": student.major,
        "grade": student.grade,
        "career_goal": student.career_goal,
        "suggested_job_code": suggested_job_code,
        "suggested_job_title": suggested_job_title,
    }


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
    experience = _extract_resume_experience_context(db, current_user.id)
    max_recommended = 30
    min_score = 60.0

    if student_profile:
        scored_profiles = []

        for jp in all_profiles:
            posting = postings.get(jp.job_code)
            scoring = _score_recommended_job(student_profile, jp, experience, posting)
            final_score = scoring["score"]
            if final_score < min_score:
                continue
            scored_profiles.append((final_score, scoring, jp, posting))

        scored_profiles.sort(key=lambda item: item[0], reverse=True)

        logger.info(
            "推荐岗位统计: 总岗位数=%s, 60分以上岗位数=%s, 项目数=%s, 实习数=%s, 将返回=%s",
            len(all_profiles),
            len(scored_profiles),
            experience["project_count"],
            experience["internship_count"],
            min(len(scored_profiles), max_recommended),
        )

        for _, scoring, jp, posting in scored_profiles[:max_recommended]:
            company_name = posting.company_name if posting else "推荐岗位"
            salary_range = posting.salary_range if posting and posting.salary_range else ""
            skills = jp.skill_requirements[:5] if jp.skill_requirements else []
            matched = list(dict.fromkeys(scoring["matched_skills"] + scoring["experience_tags"]))[:6]
            missing = scoring["missing_skills"][:4]

            if scoring["experience_reason"]:
                reason = scoring["experience_reason"]
            elif len(matched) >= 3:
                reason = f"已掌握 {', '.join(matched[:3])} 等核心技能。"
            elif len(matched) >= 1:
                reason = f"已掌握 {', '.join(matched)}，可补强 {', '.join(missing[:2])} 等技能。"
            elif scoring["potential_score"] >= 80:
                reason = "学习能力和综合素质较好，适合冲刺此方向。"
            else:
                reason = f"建议重点补齐 {', '.join(missing[:3])} 等技能。"

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
                "experience_tags": scoring["experience_tags"],
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
