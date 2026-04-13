from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import JobPosting, JobProfile, MatchDimensionScore, MatchResult, Student, StudentProfile
from app.services.matching.recommendation import (
    extract_resume_experience_context,
    score_recommended_job,
)

logger = logging.getLogger(__name__)


class MatchingService:
    def analyze_match(self, db: Session, student_id: int, job_code: str) -> dict:
        try:
            student_profile = db.scalar(select(StudentProfile).where(StudentProfile.student_id == student_id))
            job_profile = db.scalar(select(JobProfile).where(JobProfile.job_code == job_code))
            student = db.get(Student, student_id)
            if not student_profile or not job_profile or not student:
                raise ValueError("学生画像或岗位画像不存在")
            weights = job_profile.dimension_weights or {
                "basic_requirements": 0.2,
                "professional_skills": 0.4,
                "professional_literacy": 0.2,
                "development_potential": 0.2,
            }
            posting = db.scalar(select(JobPosting).where(JobPosting.job_code == job_code).limit(1))
            experience = extract_resume_experience_context(db, student.user_id, job_profile, student_profile.source_summary)
            scoring = score_recommended_job(student_profile, job_profile, experience, posting)
            scoring_dimensions = scoring["dimensions"]
            basic_score = scoring_dimensions["basic_requirements"]["score"]
            skill_score = scoring_dimensions["professional_skills"]["score"]
            literacy_score = scoring_dimensions["professional_literacy"]["score"]
            potential_score = scoring_dimensions["development_potential"]["score"]
            basic_evidence = scoring_dimensions["basic_requirements"]["evidence"]
            skill_evidence = scoring_dimensions["professional_skills"]["evidence"]
            literacy_evidence = scoring_dimensions["professional_literacy"]["evidence"]
            potential_evidence = scoring_dimensions["development_potential"]["evidence"]
            dimensions = [
                {
                    "dimension": "基础要求",
                    "score": basic_score,
                    "weight": weights["basic_requirements"],
                    "reasoning": "根据证书匹配、画像完整度和实习能力评估基础门槛。",
                    "evidence": basic_evidence,
                },
                {
                    "dimension": "职业技能",
                    "score": skill_score,
                    "weight": weights["professional_skills"],
                    "reasoning": "根据核心技能覆盖率与关键技能缺口评分。",
                    "evidence": skill_evidence,
                },
                {
                    "dimension": "职业素养",
                    "score": literacy_score,
                    "weight": weights["professional_literacy"],
                    "reasoning": "根据沟通、抗压和实习表现与岗位要求的接近程度评分。",
                    "evidence": literacy_evidence,
                },
                {
                    "dimension": "发展潜力",
                    "score": potential_score,
                    "weight": weights["development_potential"],
                    "reasoning": "根据学习能力、创新能力和画像完整度评估长期成长性。",
                    "evidence": potential_evidence,
                },
            ]
            total_score = scoring["score"]
            gap_items = []
            for skill in skill_evidence["missing_skills"]:
                gap_items.append({"type": "skill", "name": skill, "suggestion": f"优先通过课程/项目补齐 {skill}。"})
            for certificate in basic_evidence["missing_certificates"]:
                gap_items.append({"type": "certificate", "name": certificate, "suggestion": f"可将 {certificate} 纳入中期目标。"})
            suggestions = [
                "围绕缺失技能补齐 1-2 个项目案例。",
                "将简历中的项目成果量化，增强竞争力表达。",
                "按月复盘岗位技能覆盖率并更新行动计划。",
            ]
            strengths = list(dict.fromkeys(scoring["matched_skills"] + scoring["experience_tags"][:3]))
            ocr_note = ""
            if scoring.get("evidence_boost", 0) > 0:
                ocr_note = f"（含项目经历与求职意向证据加分 {scoring['evidence_boost']:.1f} 分）"
            summary = (
                f"目标岗位为 {job_profile.title}。"
                f"当前核心技能匹配度 {skill_score:.1f} 分，基础画像分 {scoring['base_score']:.1f} 分，"
                f"综合得分 {total_score:.1f} 分{ocr_note}。"
                f"优势主要体现在 {', '.join(strengths) or '项目经历与学习潜力'}，"
                f"短板集中在 {', '.join(item['name'] for item in gap_items[:3]) or '证书与项目表达'}。"
            )
            match = db.scalar(
                select(MatchResult)
                .where(MatchResult.student_profile_id == student_profile.id)
                .where(MatchResult.job_profile_id == job_profile.id)
            )
            if not match:
                match = MatchResult(student_profile_id=student_profile.id, job_profile_id=job_profile.id)
                db.add(match)
                db.flush()
            match.total_score = total_score
            match.summary = summary
            match.gaps_json = gap_items
            match.suggestions_json = suggestions
            match.dimensions_json = dimensions
            match.weights_json = weights
            match.job_code = job_code
            db.execute(delete(MatchDimensionScore).where(MatchDimensionScore.match_result_id == match.id))
            for dimension in dimensions:
                db.add(
                    MatchDimensionScore(
                        match_result_id=match.id,
                        dimension=dimension["dimension"],
                        score=dimension["score"],
                        weight=dimension["weight"],
                        reasoning=dimension["reasoning"],
                        evidence_json=dimension["evidence"],
                    )
                )
            db.commit()
            return {
                "student_id": student_id,
                "job_code": job_code,
                "total_score": total_score,
                "weights": weights,
                "dimensions": dimensions,
                "gap_items": gap_items,
                "suggestions": suggestions,
                "summary": summary,
            }
        except ValueError as e:
            logger.error(f"ValueError in analyze_match for student {student_id}, job {job_code}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in analyze_match for student {student_id}, job {job_code}: {str(e)}")
            raise ValueError(f"Failed to analyze match: {str(e)}") from e
