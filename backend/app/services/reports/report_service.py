from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.llm.providers import BaseLLMProvider
from app.models import CareerReport, GrowthTask, JobProfile, PathRecommendation, ReportVersion, Student, StudentProfile, UploadedFile
from app.services.matching.recommendation import _resume_relevance
from app.services.matching.matching_service import MatchingService
from app.services.paths.career_path_service import CareerPathService
from app.services.reports.exporters import export_markdown_to_docx, export_markdown_to_pdf

logger = logging.getLogger(__name__)


class ReportService:
    REQUIRED_SECTIONS = ["overview", "matching_analysis", "goals", "action_plan", "evidence"]

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        matching_service: MatchingService,
        career_path_service: CareerPathService,
    ) -> None:
        self.llm_provider = llm_provider
        self.matching_service = matching_service
        self.career_path_service = career_path_service
        self.settings = get_settings()

    def _check_evidence_sufficiency(self, latest_ocr: dict, match_result: dict) -> list[str]:
        """Return list of missing evidence descriptions; empty means sufficient."""
        missing: list[str] = []
        if not latest_ocr or not latest_ocr.get("raw_text"):
            missing.append("简历 OCR 解析结果为空，无法提取真实经历与技能证据")
        if not match_result or not match_result.get("dimensions"):
            missing.append("匹配结果维度数据为空，无法生成评分分析")
        return missing

    async def generate_report(self, db: Session, student_id: int, job_code: str) -> dict:
        student = db.get(Student, student_id)
        student_profile = db.scalar(select(StudentProfile).where(StudentProfile.student_id == student_id))
        job_profile = db.scalar(select(JobProfile).where(JobProfile.job_code == job_code))
        if not student or not student_profile or not job_profile:
            raise ValueError("生成报告前请先准备学生画像与岗位画像")
        latest_ocr = self._latest_resume_ocr(db, student.user_id, job_profile, student_profile.source_summary)
        student_name = self._student_name_from_ocr(student, latest_ocr)
        report = db.scalar(
            select(CareerReport)
            .where(CareerReport.student_id == student_id)
            .where(CareerReport.target_job_code == job_code)
        )
        if (
            report
            and report.content_json
            and report.markdown_content
            and report.updated_at
            and student_profile.updated_at
            and report.updated_at >= student_profile.updated_at
            and self._report_matches_current_resume(report, student_name, latest_ocr)
            and "OCR 项目/意向加权" in report.markdown_content
        ):
            return {
                "report_id": report.id,
                "student_id": student_id,
                "job_code": job_code,
                "content": report.content_json,
                "markdown_content": report.markdown_content,
                "status": report.status,
                "path_recommendation_id": report.path_recommendation_id,
            }
        match_result = self.matching_service.analyze_match(db, student_id, job_code)
        path_result = await self.career_path_service.plan_path(db, student_id, job_code)

        # Evidence sufficiency check — return insufficient_data before calling LLM
        evidence_gaps = self._check_evidence_sufficiency(latest_ocr, match_result)
        if evidence_gaps:
            insufficient_content = {
                "overview": "",
                "matching_analysis": {},
                "goals": {},
                "action_plan": {},
                "evidence": {"missing": evidence_gaps},
            }
            insufficient_md = (
                "# CareerPilot 职业发展报告\n\n"
                "> **资料不足，无法生成完整报告**\n\n"
                "以下关键证据缺失，请补充后重试：\n"
            )
            for gap in evidence_gaps:
                insufficient_md += f"- {gap}\n"
            insufficient_md += (
                "\n建议：请先上传简历并完成 OCR 解析，确保匹配分析数据可用。"
            )
            # Persist insufficient_data status so frontend can react
            if not report:
                report = CareerReport(student_id=student_id, target_job_code=job_code)
                db.add(report)
                db.flush()
            report.content_json = insufficient_content
            report.markdown_content = insufficient_md
            report.status = "insufficient_data"
            db.commit()
            return {
                "report_id": report.id,
                "student_id": student_id,
                "job_code": job_code,
                "content": report.content_json,
                "markdown_content": report.markdown_content,
                "status": report.status,
                "path_recommendation_id": report.path_recommendation_id,
            }

        # Look up the PathRecommendation that plan_path just created/updated
        path_rec = db.scalar(
            select(PathRecommendation)
            .where(PathRecommendation.student_id == student_id)
            .where(PathRecommendation.target_job_code == job_code)
        )

        # 从evidence中提取专业信息来源
        major_source = "学生基本信息"
        if student_profile.evidence_summary and "sources" in student_profile.evidence_summary:
            sources = student_profile.evidence_summary.get("sources", "")
            if "OCR" in sources or "解析" in sources:
                major_source = "OCR解析"
        if self._ocr_structured(latest_ocr).get("major"):
            major_source = "OCR解析"

        llm_result = await self.llm_provider.generate_report(
            {
                "student_name": student_name,
                "student_major": self._student_major_from_ocr(student, student_profile, latest_ocr),
                "student_major_source": major_source,
                "resume_intent": self._resume_intent_from_ocr(latest_ocr),
                "resume_evidence": self._resume_evidence_from_ocr(latest_ocr),
                "student_profile": {
                    "skills": student_profile.skills_json,
                    "certificates": student_profile.certificates_json,
                    "capability_scores": student_profile.capability_scores,
                    "completeness_score": student_profile.completeness_score,
                },
                "job_profile": {
                    "job_code": job_profile.job_code,
                    "title": job_profile.title,
                    "summary": job_profile.summary,
                    "skill_requirements": job_profile.skill_requirements,
                },
                "job_title": job_profile.title,
                "match_result": match_result,
                "path_result": path_result,
            }
        )
        report = db.scalar(
            select(CareerReport)
            .where(CareerReport.student_id == student_id)
            .where(CareerReport.target_job_code == job_code)
        )
        if not report:
            report = CareerReport(student_id=student_id, target_job_code=job_code)
            db.add(report)
            db.flush()
        if path_rec:
            report.path_recommendation_id = path_rec.id
        report.content_json = llm_result["content"]
        report.markdown_content = llm_result["markdown_content"]
        report.status = "generated"
        version_count = len(list(db.scalars(select(ReportVersion).where(ReportVersion.report_id == report.id)).all()))
        db.add(
            ReportVersion(
                report_id=report.id,
                version_no=version_count + 1,
                content_json=report.content_json,
                markdown_content=report.markdown_content,
                editor_notes="系统自动生成",
            )
        )
        self._sync_growth_tasks(db, report.id, student_id, report.content_json["action_plan"])
        db.commit()
        return {
            "report_id": report.id,
            "student_id": student_id,
            "job_code": job_code,
            "content": report.content_json,
            "markdown_content": report.markdown_content,
            "status": report.status,
            "path_recommendation_id": report.path_recommendation_id,
        }

    def _latest_resume_ocr(self, db: Session, owner_id: int, job_profile: JobProfile | None = None, source_summary: str = "") -> dict:
        uploads = list(db.scalars(
            select(UploadedFile)
            .where(UploadedFile.owner_id == owner_id)
            .where(UploadedFile.file_type == "resume")
            .order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())
            .limit(8)
        ).all())
        if not uploads:
            return {}
        if source_summary:
            source_names = {item.strip() for item in source_summary.split("；") if item.strip()}
            sourced_uploads = [upload for upload in uploads if upload.file_name in source_names]
            if sourced_uploads:
                uploads = sourced_uploads
        if job_profile:
            ranked = []
            for uploaded in uploads:
                ocr = (uploaded.meta_json or {}).get("ocr_result") or (uploaded.meta_json or {}).get("ocr")
                if isinstance(ocr, dict):
                    ranked.append((_resume_relevance(ocr, job_profile), ocr))
            ranked.sort(key=lambda item: item[0], reverse=True)
            if ranked and ranked[0][0] > 0:
                return ranked[0][1]

        uploaded = uploads[0]
        if not uploaded.meta_json:
            return {}
        ocr = uploaded.meta_json.get("ocr_result") or uploaded.meta_json.get("ocr")
        return ocr if isinstance(ocr, dict) else {}

    def _report_matches_current_resume(self, report: CareerReport, student_name: str, ocr: dict) -> bool:
        raw_text = self._ocr_raw_text(ocr)
        if raw_text and student_name and student_name not in report.markdown_content:
            return False
        intent_job = self._resume_intent_from_ocr(ocr).get("job")
        if intent_job and intent_job not in report.markdown_content and report.target_job_code == "J-FE-001":
            return False
        return True

    def _ocr_structured(self, ocr: dict) -> dict:
        structured = ocr.get("structured_json") if isinstance(ocr, dict) else {}
        return structured if isinstance(structured, dict) else {}

    def _ocr_raw_text(self, ocr: dict) -> str:
        raw_text = ocr.get("raw_text") if isinstance(ocr, dict) else ""
        return raw_text if isinstance(raw_text, str) else ""

    def _student_name_from_ocr(self, student: Student, ocr: dict) -> str:
        structured = self._ocr_structured(ocr)
        structured_name = str(structured.get("name") or "").strip()
        if structured_name and structured_name != "未知学生":
            return structured_name

        for line in self._ocr_raw_text(ocr).splitlines():
            candidate = line.strip()
            if re.fullmatch(r"[\u4e00-\u9fa5·]{2,8}", candidate):
                return candidate

        if hasattr(student, "user") and student.user and student.user.full_name:
            return student.user.full_name
        return f"学生{student.id}"

    def _student_major_from_ocr(self, student: Student, student_profile: StudentProfile, ocr: dict) -> str:
        structured = self._ocr_structured(ocr)
        major = str(structured.get("major") or "").strip()
        if major:
            return major
        if student_profile.source_summary:
            return student_profile.source_summary
        return student.major

    def _resume_intent_from_ocr(self, ocr: dict) -> dict:
        raw_text = self._ocr_raw_text(ocr)
        intent: dict[str, str] = {}
        patterns = {
            "job": r"意向岗位[:：\s]*([^\n]+)",
            "city": r"意向城市[:：\s]*([^\n]+)",
            "salary": r"期望薪资[:：\s]*([^\n]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, raw_text)
            if match:
                value = re.split(r"\s{2,}|意向城市|期望薪资|求职类型", match.group(1).strip())[0].strip(" ：:")
                if value:
                    intent[key] = value
        return intent

    def _resume_evidence_from_ocr(self, ocr: dict) -> dict:
        structured = self._ocr_structured(ocr)
        return {
            "name": structured.get("name"),
            "major": structured.get("major"),
            "skills": structured.get("skills") or [],
            "projects": structured.get("projects") or [],
            "internships": structured.get("internships") or [],
            "raw_excerpt": self._ocr_raw_text(ocr)[:1200],
        }

    def _sync_growth_tasks(self, db: Session, report_id: int, student_id: int, action_plan: dict) -> None:
        for item in action_plan.get("short_term", []):
            db.add(
                GrowthTask(
                    student_id=student_id,
                    report_id=report_id,
                    title=item,
                    phase="short_term",
                    metric="阶段技能覆盖率提升",
                    status="pending",
                )
            )
        for item in action_plan.get("mid_term", []):
            db.add(
                GrowthTask(
                    student_id=student_id,
                    report_id=report_id,
                    title=item,
                    phase="mid_term",
                    metric="项目/实习成果达成",
                    status="pending",
                )
            )

    def get_report(self, db: Session, report_id: int) -> CareerReport:
        report = db.get(CareerReport, report_id)
        if not report:
            raise ValueError("报告不存在")
        return report

    async def polish_report(self, db: Session, report_id: int, markdown_content: str) -> dict:
        report = self.get_report(db, report_id)
        polished = await self.llm_provider.polish_markdown(markdown_content)
        report.markdown_content = polished
        report.status = "polished"
        version_count = len(list(db.scalars(select(ReportVersion).where(ReportVersion.report_id == report.id)).all()))
        db.add(
            ReportVersion(
                report_id=report.id,
                version_no=version_count + 1,
                content_json=report.content_json,
                markdown_content=polished,
                editor_notes="智能润色",
            )
        )
        db.commit()
        return {
            "report_id": report.id,
            "student_id": report.student_id,
            "job_code": report.target_job_code,
            "content": report.content_json,
            "markdown_content": polished,
            "status": report.status,
        }

    def check_completeness(self, db: Session, report_id: int) -> dict:
        try:
            report = self.get_report(db, report_id)
            missing = [section for section in self.REQUIRED_SECTIONS if section not in report.content_json]
            suggestions = []
            if "matching_analysis" in missing:
                suggestions.append("补充职业探索与岗位匹配分析。")
            if "goals" in missing:
                suggestions.append("补充职业目标和路径规划。")
            if "action_plan" in missing:
                suggestions.append("补充短期、中期行动计划与评估指标。")
            if "evidence" in missing:
                suggestions.append("补充岗位画像、学生画像、路径推荐依据。")
            return {
                "report_id": report_id,
                "is_complete": len(missing) == 0,
                "missing_sections": missing,
                "suggestions": suggestions or ["报告结构完整，可直接导出。"],
            }
        except ValueError as e:
            logger.error(f"ValueError while checking report completeness for {report_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to check completeness for report {report_id}: {str(e)}")
            raise ValueError(f"Failed to check report completeness: {str(e)}") from e

    def export_report(self, db: Session, report_id: int, export_format: str) -> dict:
        try:
            report = self.get_report(db, report_id)
            suffix = "pdf" if export_format == "pdf" else "docx"
            file_name = f"career_report_{report_id}.{suffix}"
            output_path = self.settings.export_path / file_name
            if export_format == "pdf":
                export_markdown_to_pdf(report.markdown_content, output_path)
            else:
                export_markdown_to_docx(report.markdown_content, output_path)
            return {"format": export_format, "path": str(output_path), "file_name": file_name}
        except ValueError as e:
            logger.error(f"ValueError while exporting report {report_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to export report {report_id} as {export_format}: {str(e)}")
            raise ValueError(f"Failed to export report: {str(e)}") from e
