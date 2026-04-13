from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.ocr.providers import _normalize_for_match, _normalize_ocr_text
from app.models import JobPosting, JobProfile, StudentProfile, UploadedFile
from app.services.matching.scoring import (
    score_basic_requirements,
    score_development_potential,
    score_professional_literacy,
    score_professional_skills,
)


EXPERIENCE_KEYWORDS = [
    "AI", "算法", "机器学习", "深度学习", "PyTorch", "TensorFlow", "模型", "建模", "数据",
    "分析", "SQL", "Python", "Java", "JavaScript", "TypeScript", "React", "Vue",
    "前端", "后端", "接口", "API", "FastAPI", "测试", "自动化", "运维", "Linux",
    "产品", "需求", "原型", "可视化", "统计", "项目", "实习",
]


def safe_list(value: object) -> list[str]:
    return [str(item).strip() for item in value or [] if str(item).strip()]


def _resume_relevance(ocr: dict, job_profile: JobProfile) -> float:
    structured = ocr.get("structured_json") or {}
    raw_text = _normalize_ocr_text(str(ocr.get("raw_text") or ""))
    target_text = _normalize_for_match(" ".join([
        str(structured.get("target_job") or ""),
        raw_text[:2000],
    ]))
    title = _normalize_for_match(job_profile.title or "")
    score = 0.0
    if title and title in target_text:
        score += 20
    for token in ("数据分析", "数据处理", "后端开发", "算法", "人工智能", "前端开发", "产品"):
        normalized = _normalize_for_match(token)
        if normalized in title and normalized in target_text:
            score += 12
    for skill in safe_list(job_profile.skill_requirements):
        if _normalize_for_match(skill) in target_text:
            score += 1
    return score


def extract_resume_experience_context(
    db: Session,
    owner_id: int,
    job_profile: JobProfile | None = None,
    source_summary: str = "",
) -> dict:
    files = list(db.scalars(
        select(UploadedFile)
        .where(UploadedFile.owner_id == owner_id)
        .order_by(UploadedFile.created_at.desc())
        .limit(8)
    ).all())
    if source_summary:
        source_names = {item.strip() for item in source_summary.split("；") if item.strip()}
        sourced_files = [file for file in files if file.file_name in source_names]
        if sourced_files:
            files = sourced_files
    if job_profile and files:
        ranked = []
        for file in files:
            ocr = (file.meta_json or {}).get("ocr") if file.meta_json else None
            if ocr:
                ranked.append((_resume_relevance(ocr, job_profile), file))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0] > 0:
            files = [ranked[0][1]]
    elif files:
        files = files[:1]

    projects: list[str] = []
    internships: list[str] = []
    target_jobs: list[str] = []
    raw_sections: list[str] = []
    full_texts: list[str] = []
    section_markers = ("项目经历", "项目经验", "项目实践", "实习经历", "实习经验", "工作经历", "实践经历")

    for file in files:
        ocr = (file.meta_json or {}).get("ocr") if file.meta_json else None
        if not ocr:
            continue
        structured = ocr.get("structured_json") or {}
        projects.extend(safe_list(structured.get("projects")))
        internships.extend(safe_list(structured.get("internships")))
        if structured.get("target_job"):
            target_jobs.append(str(structured.get("target_job")))

        raw_text = _normalize_ocr_text(str(ocr.get("raw_text") or ""))
        if raw_text:
            full_texts.append(raw_text[:5000])
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            if any(marker in line for marker in section_markers):
                raw_sections.extend(lines[idx: idx + 18])

    project_text = "；".join(dict.fromkeys(projects + raw_sections + full_texts))
    internship_text = "；".join(dict.fromkeys(internships))
    combined = f"{project_text}；{internship_text}".strip("；")
    return {
        "text": combined,
        "projects": projects,
        "internships": internships,
        "target_jobs": list(dict.fromkeys(target_jobs)),
        "project_count": len([item for item in projects if len(item) > 2]),
        "internship_count": len([item for item in internships if len(item) > 2]),
    }


def score_experience_context(experience: dict, job_profile: JobProfile, posting: JobPosting | None) -> dict:
    text = str(experience.get("text") or "")
    if not text:
        return {"score": 0.0, "tags": [], "reason": ""}

    lowered_text = text.lower()
    compact_text = lowered_text.replace(" ", "")
    required_skills = safe_list(job_profile.skill_requirements)
    matched_skills = [
        skill for skill in required_skills
        if skill.lower() in lowered_text or skill.replace(" ", "").lower() in compact_text
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
    reason = f"项目/实习经历中匹配到 {', '.join(tags[:4])}。" if tags else ""
    return {"score": round(min(100.0, score), 1), "tags": tags, "reason": reason}


def score_target_intent(experience: dict, job_profile: JobProfile) -> dict:
    target_text = _normalize_for_match(" ".join(safe_list(experience.get("target_jobs"))))
    if not target_text:
        return {"score": 0.0, "tags": []}

    title = _normalize_for_match(job_profile.title or "")
    intent_rules = [
        ("数据分析", ("数据分析", "商业分析", "数据产品")),
        ("数据处理", ("数据分析", "数据工程", "数据产品", "后端")),
        ("后端开发", ("后端", "全栈", "数据工程")),
        ("算法", ("算法", "AI", "机器学习")),
        ("人工智能", ("算法", "AI", "机器学习")),
        ("前端开发", ("前端", "全栈")),
        ("产品", ("产品", "数据产品")),
    ]
    matched: list[str] = []
    for intent, title_keywords in intent_rules:
        if intent in target_text and any(_normalize_for_match(keyword) in title for keyword in title_keywords):
            matched.append(intent)

    if not matched:
        return {"score": 0.0, "tags": []}
    return {"score": min(10.0, 5.0 + len(matched) * 3.0), "tags": matched[:4]}


def score_recommended_job(
    student_profile: StudentProfile,
    job_profile: JobProfile,
    experience: dict | None = None,
    posting: JobPosting | None = None,
) -> dict:
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
    literacy_score, literacy_evidence = score_professional_literacy(student_data, job_data)
    potential_score, potential_evidence = score_development_potential(student_data, job_data)
    base_score = round(
        basic_score * weights.get("basic_requirements", 0.2)
        + skill_score * weights.get("professional_skills", 0.4)
        + literacy_score * weights.get("professional_literacy", 0.2)
        + potential_score * weights.get("development_potential", 0.2),
        1,
    )
    experience_result = score_experience_context(experience or {}, job_profile, posting)
    intent_result = score_target_intent(experience or {}, job_profile)

    # Fold OCR evidence into the four dimension scores as evidence enhancement
    exp_bonus = round(experience_result["score"] * 0.28, 1)
    intent_bonus = round(intent_result["score"], 1)
    evidence_boost = round(exp_bonus + intent_bonus, 1)

    # Distribute evidence boost across dimensions proportionally to weights
    basic_score = min(100.0, round(basic_score + evidence_boost, 1))
    skill_score = min(100.0, round(skill_score + evidence_boost, 1))
    literacy_score = min(100.0, round(literacy_score + evidence_boost, 1))
    potential_score = min(100.0, round(potential_score + evidence_boost, 1))

    final_score = round(
        basic_score * weights.get("basic_requirements", 0.2)
        + skill_score * weights.get("professional_skills", 0.4)
        + literacy_score * weights.get("professional_literacy", 0.2)
        + potential_score * weights.get("development_potential", 0.2),
        1,
    )

    # Attach OCR evidence to relevant dimensions
    basic_evidence["experience_tags"] = experience_result.get("tags", [])
    skill_evidence["experience_tags"] = experience_result.get("tags", [])
    literacy_evidence["experience_tags"] = experience_result.get("tags", [])
    potential_evidence["intent_tags"] = intent_result.get("tags", [])
    potential_evidence["intent_bonus"] = intent_bonus

    return {
        "score": final_score,
        "base_score": base_score,
        "experience_score": experience_result["score"],
        "experience_tags": experience_result["tags"],
        "experience_reason": experience_result["reason"],
        "intent_bonus": intent_result["score"],
        "intent_tags": intent_result["tags"],
        "matched_skills": skill_evidence.get("matched_skills", []),
        "missing_skills": skill_evidence.get("missing_skills", []),
        "matched_certificates": basic_evidence.get("matched_certificates", []),
        "missing_certificates": basic_evidence.get("missing_certificates", []),
        "skill_score": round(skill_score, 1),
        "potential_score": round(potential_score, 1),
        "evidence_boost": evidence_boost,
        "dimensions": {
            "basic_requirements": {"score": basic_score, "evidence": basic_evidence},
            "professional_skills": {"score": skill_score, "evidence": skill_evidence},
            "professional_literacy": {"score": literacy_score, "evidence": literacy_evidence},
            "development_potential": {"score": potential_score, "evidence": potential_evidence},
        },
    }
