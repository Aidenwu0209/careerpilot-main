import pytest

from app.models import UploadedFile
from app.schemas.profile import ManualStudentInput
from app.services.bootstrap import create_service_container, initialize_demo_data


@pytest.mark.asyncio
async def test_report_insufficient_data_without_ocr(db_session):
    """When no OCR data exists, report generation should return insufficient_data status."""
    container = create_service_container()
    await initialize_demo_data(db_session, container)
    await container.student_profile_service.generate_profile(
        db_session,
        student_id=1,
        uploaded_file_ids=[],
        manual_input=ManualStudentInput(
            target_job="前端开发工程师",
            self_introduction="希望成为前端工程师",
            skills=["JavaScript", "TypeScript", "React", "Next.js"],
            certificates=["英语四级"],
            projects=["CareerPilot"],
            internships=["前端开发实习"],
        ),
    )
    result = await container.report_service.generate_report(db_session, 1, "J-FE-001")
    assert result["status"] == "insufficient_data"
    assert result["report_id"] == 0
    assert len(result["missing_evidence"]) > 0
    assert any("OCR" in m for m in result["missing_evidence"])


@pytest.mark.asyncio
async def test_report_completeness_logic(db_session):
    """When OCR data exists, report should generate successfully and pass completeness check."""
    container = create_service_container()
    await initialize_demo_data(db_session, container)

    # Create a mock uploaded file with OCR data so _latest_resume_ocr finds it
    upload = UploadedFile(
        owner_id=1,
        file_type="resume",
        file_name="test_resume.pdf",
        storage_key="test/test_resume.pdf",
        meta_json={
            "ocr_result": {
                "raw_text": "张三 前端开发 JavaScript React 项目经历",
                "structured_json": {
                    "name": "张三",
                    "major": "计算机科学与技术",
                    "skills": ["JavaScript", "React"],
                    "projects": ["CareerPilot"],
                    "internships": [],
                    "certificates": [],
                },
            }
        },
    )
    db_session.add(upload)
    db_session.flush()

    # Generate profile with manual input only (no file parsing)
    await container.student_profile_service.generate_profile(
        db_session,
        student_id=1,
        uploaded_file_ids=[],
        manual_input=ManualStudentInput(
            target_job="前端开发工程师",
            self_introduction="希望成为前端工程师",
            skills=["JavaScript", "TypeScript", "React", "Next.js"],
            certificates=["英语四级"],
            projects=["CareerPilot"],
            internships=["前端开发实习"],
        ),
    )
    report = await container.report_service.generate_report(db_session, 1, "J-FE-001")
    assert report["status"] != "insufficient_data"
    completeness = container.report_service.check_completeness(db_session, report["report_id"])
    assert completeness["is_complete"] is True
    assert completeness["missing_sections"] == []
