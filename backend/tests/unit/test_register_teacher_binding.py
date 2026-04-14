from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Student, Teacher, TeacherStudentLink, User


def test_student_register_with_teacher_code_creates_link(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "new_student_bound",
            "password": "demo123",
            "full_name": "新同学",
            "role": "student",
            "email": "new_student_bound@careerpilot.local",
            "teacher_code": "teacher_demo",
        },
    )
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "new_student_bound"))
        assert user is not None
        assert user.email == "new_student_bound@careerpilot.local"

        student = db.scalar(select(Student).where(Student.user_id == user.id))
        assert student is not None

        teacher_user = db.scalar(select(User).where(User.username == "teacher_demo"))
        teacher = db.scalar(select(Teacher).where(Teacher.user_id == teacher_user.id))
        link = db.scalar(
            select(TeacherStudentLink).where(
                TeacherStudentLink.teacher_id == teacher.id,
                TeacherStudentLink.student_id == student.id,
                TeacherStudentLink.status == "active",
            )
        )
        assert link is not None
        assert link.source == "invite_code"
        assert link.group_name == "自助注册"


def test_student_register_with_unknown_teacher_code_fails(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "new_student_unbound",
            "password": "demo123",
            "full_name": "未绑定同学",
            "role": "student",
            "email": "new_student_unbound@careerpilot.local",
            "teacher_code": "missing_teacher",
        },
    )
    assert resp.status_code == 400
    assert "未找到对应老师" in resp.text
