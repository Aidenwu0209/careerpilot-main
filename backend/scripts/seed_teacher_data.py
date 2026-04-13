"""
Seed the database with diverse student data so that the teacher dashboard
has meaningful content to display.

Run:  cd backend && python scripts/seed_teacher_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows UTF-8 console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models import (
    CareerReport,
    JobProfile,
    MatchDimensionScore,
    MatchResult,
    Student,
    StudentProfile,
    User,
)
from app.services.auth_service import hash_password

# ---------------------------------------------------------------------------
# Configuration – 10 diverse students
# ---------------------------------------------------------------------------

STUDENTS = [
    {
        "username": "student_liwei",
        "full_name": "李伟",
        "major": "计算机科学与技术",
        "grade": "大三",
        "career_goal": "AI 算法工程师",
        "target_job_code": "J-AI-001",
        "target_job_title": "AI 算法工程师",
        "skills": ["Python", "TensorFlow", "PyTorch", "机器学习", "数据结构", "线性代数"],
        "score": 88,
        "report_status": "completed",
    },
    {
        "username": "student_zhangmin",
        "full_name": "张敏",
        "major": "软件工程",
        "grade": "大四",
        "career_goal": "产品经理",
        "target_job_code": "J-PM-001",
        "target_job_title": "产品经理",
        "skills": ["需求分析", "Axure", "用户调研", "数据驱动", "项目管理"],
        "score": 76,
        "report_status": "completed",
    },
    {
        "username": "student_wangfang",
        "full_name": "王芳",
        "major": "数据科学与大数据技术",
        "grade": "大三",
        "career_goal": "数据分析师",
        "target_job_code": "J-DA-001",
        "target_job_title": "数据分析师",
        "skills": ["Python", "SQL", "Tableau", "统计学", "Excel", "数据可视化"],
        "score": 92,
        "report_status": "completed",
    },
    {
        "username": "student_liuyang",
        "full_name": "刘洋",
        "major": "软件工程",
        "grade": "大三",
        "career_goal": "后端开发工程师",
        "target_job_code": "J-BE-001",
        "target_job_title": "后端开发工程师",
        "skills": ["Java", "Spring Boot", "MySQL", "Redis", "微服务", "Docker"],
        "score": 81,
        "report_status": "completed",
    },
    {
        "username": "student_chenxiao",
        "full_name": "陈晓",
        "major": "数字媒体技术",
        "grade": "大四",
        "career_goal": "UI/UX 设计师",
        "target_job_code": "J-UI-001",
        "target_job_title": "UI/UX 设计师",
        "skills": ["Figma", "Sketch", "Photoshop", "交互设计", "用户研究"],
        "score": 73,
        "report_status": "edited",
    },
    {
        "username": "student_zhaolei",
        "full_name": "赵磊",
        "major": "信息安全",
        "grade": "大三",
        "career_goal": "运维工程师",
        "target_job_code": "J-OPS-001",
        "target_job_title": "运维工程师",
        "skills": ["Linux", "Shell", "Kubernetes", "CI/CD", "网络协议"],
        "score": 65,
        "report_status": "draft",
    },
    {
        "username": "student_sunli",
        "full_name": "孙丽",
        "major": "电子商务",
        "grade": "大二",
        "career_goal": "数据产品经理",
        "target_job_code": "J-DPM-001",
        "target_job_title": "数据产品经理",
        "skills": ["需求分析", "SQL", "数据可视化", "市场调研", "竞品分析"],
        "score": 55,
        "report_status": "draft",
    },
    {
        "username": "student_zhoujie",
        "full_name": "周杰",
        "major": "计算机科学与技术",
        "grade": "大四",
        "career_goal": "全栈工程师",
        "target_job_code": "J-FS-001",
        "target_job_title": "全栈工程师",
        "skills": ["React", "Node.js", "TypeScript", "MongoDB", "GraphQL", "Docker"],
        "score": 85,
        "report_status": "completed",
    },
    {
        "username": "student_wuhan",
        "full_name": "吴涵",
        "major": "软件工程",
        "grade": "大三",
        "career_goal": "测试工程师",
        "target_job_code": "J-QA-001",
        "target_job_title": "测试工程师",
        "skills": ["Selenium", "JMeter", "Python", "自动化测试", "性能测试"],
        "score": 70,
        "report_status": "completed",
    },
    {
        "username": "student_huangyu",
        "full_name": "黄宇",
        "major": "网络工程",
        "grade": "大二",
        "career_goal": "前端开发工程师",
        "target_job_code": "J-FE-001",
        "target_job_title": "前端开发工程师",
        "skills": ["HTML/CSS", "JavaScript", "Vue.js", "React 基础"],
        "score": 48,
        "report_status": "draft",
    },
]

# Gap items for generating realistic match analysis
GAP_POOL = {
    "J-AI-001": [
        {"item": "深度学习框架经验", "name": "深度学习框架经验"},
        {"item": "论文发表经历", "name": "论文发表经历"},
        {"item": "GPU 集群使用", "name": "GPU 集群使用"},
    ],
    "J-PM-001": [
        {"item": "B端产品经验", "name": "B端产品经验"},
        {"item": "数据分析深度", "name": "数据分析深度"},
        {"item": "跨部门协调能力", "name": "跨部门协调能力"},
    ],
    "J-DA-001": [
        {"item": "大数据平台经验", "name": "大数据平台经验"},
        {"item": "A/B 测试实践", "name": "A/B 测试实践"},
    ],
    "J-BE-001": [
        {"item": "高并发架构经验", "name": "高并发架构经验"},
        {"item": "分布式系统设计", "name": "分布式系统设计"},
        {"item": "消息队列使用", "name": "消息队列使用"},
    ],
    "J-UI-001": [
        {"item": "设计系统搭建", "name": "设计系统搭建"},
        {"item": "动效设计能力", "name": "动效设计能力"},
        {"item": "前端开发基础", "name": "前端开发基础"},
    ],
    "J-OPS-001": [
        {"item": "云原生经验", "name": "云原生经验"},
        {"item": "监控体系建设", "name": "监控体系建设"},
        {"item": "安全运维实践", "name": "安全运维实践"},
    ],
    "J-DPM-001": [
        {"item": "SQL 高级查询", "name": "SQL 高级查询"},
        {"item": "数据仓库设计", "name": "数据仓库设计"},
        {"item": "指标体系搭建", "name": "指标体系搭建"},
    ],
    "J-FS-001": [
        {"item": "系统设计能力", "name": "系统设计能力"},
        {"item": "DevOps 实践", "name": "DevOps 实践"},
    ],
    "J-QA-001": [
        {"item": "接口自动化", "name": "接口自动化"},
        {"item": "安全测试经验", "name": "安全测试经验"},
    ],
    "J-FE-001": [
        {"item": "TypeScript 熟练度", "name": "TypeScript 熟练度"},
        {"item": "工程化工具链", "name": "工程化工具链"},
        {"item": "性能优化经验", "name": "性能优化经验"},
    ],
}

SUGGESTION_POOL = {
    "J-AI-001": ["参加 Kaggle 竞赛积累实战经验", "学习 Transformer 架构原理", "阅读顶会论文并复现"],
    "J-PM-001": ["参与实际产品迭代项目", "学习 SQL 进行数据驱动决策", "练习撰写 PRD 文档"],
    "J-DA-001": ["深入学习统计学建模方法", "参加数据分析实习", "学习 Spark 大数据处理"],
    "J-BE-001": ["学习分布式系统设计原理", "搭建微服务架构练习项目", "深入学习 MySQL 调优"],
    "J-UI-001": ["学习 CSS 动画和交互原型", "建立个人设计作品集", "学习基础前端开发"],
    "J-OPS-001": ["考取 CKA 认证", "学习 Prometheus + Grafana 监控", "搭建个人 Kubernetes 集群"],
    "J-DPM-001": ["深入学习数据仓库理论", "练习 SQL 复杂查询", "学习 BI 工具高级用法"],
    "J-FS-001": ["参与开源全栈项目", "学习系统设计面试题", "实践 CI/CD 流水线"],
    "J-QA-001": ["学习 pytest 框架高级用法", "实践接口自动化测试", "学习安全测试基础知识"],
    "J-FE-001": ["系统学习 TypeScript", "学习 Webpack/Vite 工程化", "参与前端开源项目"],
}

DIMENSIONS = ["skill", "certificate", "innovation", "learning", "resilience", "communication", "internship"]
DIMENSION_WEIGHTS = [0.25, 0.10, 0.10, 0.10, 0.10, 0.15, 0.20]


def _random_dim_scores(total: float) -> list[dict]:
    """Generate dimension scores that roughly sum to total (out of 100)."""
    import random
    random.seed(hash(str(total)))
    scores = []
    for i, dim in enumerate(DIMENSIONS):
        w = DIMENSION_WEIGHTS[i]
        # Make individual dimension scores vary
        base = total * random.uniform(0.7, 1.3)
        base = min(100, max(0, base))
        scores.append({
            "dimension": dim,
            "score": round(base, 1),
            "weight": w,
            "reasoning": f"{dim} 维度评估分数 {round(base, 1)}",
        })
    return scores


def seed() -> None:
    db: Session = SessionLocal()
    try:
        # Check which student usernames already exist
        existing = set(
            row[0]
            for row in db.execute(select(User.username)).fetchall()
        )

        now = datetime.now(timezone.utc)
        created_count = 0

        for cfg in STUDENTS:
            if cfg["username"] in existing:
                print(f"  [skip] {cfg['username']} already exists")
                continue

            # 1. Create User
            user = User(
                username=cfg["username"],
                password_hash=hash_password("demo123"),
                role="student",
                full_name=cfg["full_name"],
                email="",
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()

            # 2. Create Student
            student = Student(
                user_id=user.id,
                major=cfg["major"],
                grade=cfg["grade"],
                career_goal=cfg["career_goal"],
                target_job_code=cfg["target_job_code"],
                target_job_title=cfg["target_job_title"],
                learning_preferences={"preferred_roles": [cfg["career_goal"]]},
                created_at=now,
                updated_at=now,
            )
            db.add(student)
            db.flush()

            # 3. Create StudentProfile
            sp = StudentProfile(
                student_id=student.id,
                source_summary=f"基于{cfg['major']}专业背景和目标岗位 {cfg['target_job_title']} 的综合评估",
                skills_json=cfg["skills"],
                certificates_json=[],
                capability_scores={
                    "skill": round(cfg["score"] * 0.9, 1),
                    "certificate": round(cfg["score"] * 0.7, 1),
                    "innovation": round(cfg["score"] * 0.85, 1),
                    "learning": round(cfg["score"] * 0.88, 1),
                    "resilience": round(cfg["score"] * 0.82, 1),
                    "communication": round(cfg["score"] * 0.78, 1),
                    "internship": round(cfg["score"] * 0.6, 1),
                },
                completeness_score=round(cfg["score"] * 0.8, 1),
                competitiveness_score=round(cfg["score"] * 0.75, 1),
                willingness_json={},
                evidence_summary={},
                created_at=now,
                updated_at=now,
            )
            db.add(sp)
            db.flush()

            # 4. Lookup JobProfile
            jp = db.scalar(
                select(JobProfile).where(JobProfile.job_code == cfg["target_job_code"]).limit(1)
            )
            if not jp:
                print(f"  [warn] JobProfile not found for {cfg['target_job_code']}, skipping match/report")
                continue

            # 5. Create MatchResult
            gaps = GAP_POOL.get(cfg["target_job_code"], [])
            suggestions = SUGGESTION_POOL.get(cfg["target_job_code"], [])
            score = cfg["score"]

            mr = MatchResult(
                student_profile_id=sp.id,
                job_profile_id=jp.id,
                total_score=score,
                summary=f"与{cfg['target_job_title']}岗位的整体匹配度为 {score} 分。",
                gaps_json=gaps,
                suggestions_json=suggestions,
                created_at=now,
                updated_at=now,
            )
            db.add(mr)
            db.flush()

            # 6. Create MatchDimensionScores
            dim_scores = _random_dim_scores(score)
            for ds in dim_scores:
                db.add(MatchDimensionScore(
                    match_result_id=mr.id,
                    dimension=ds["dimension"],
                    score=ds["score"],
                    weight=ds["weight"],
                    reasoning=ds["reasoning"],
                    created_at=now,
                    updated_at=now,
                ))

            # 7. Create CareerReport
            report_status = cfg["report_status"]
            markdown = _generate_report_markdown(cfg, score, gaps, suggestions)

            cr = CareerReport(
                student_id=student.id,
                target_job_code=cfg["target_job_code"],
                path_recommendation_id=None,
                content_json={},
                markdown_content=markdown,
                status=report_status,
                created_at=now,
                updated_at=now,
            )
            db.add(cr)

            created_count += 1
            status_label = {"draft": "进行中", "edited": "已完成", "completed": "已完成"}.get(report_status, report_status)
            print(f"  [ok] {cfg['full_name']} — {cfg['target_job_title']} — {score}分 — {status_label}")

        db.commit()
        print(f"\nDone! Created {created_count} students.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _generate_report_markdown(cfg: dict, score: float, gaps: list, suggestions: list) -> str:
    name = cfg["full_name"]
    job = cfg["target_job_title"]
    gap_text = "、".join(g.get("item", "") for g in gaps[:3]) if gaps else "无"
    sug_text = "\n".join(f"- {s}" for s in suggestions) if suggestions else "- 持续提升专业技能"

    level = "优秀" if score >= 85 else "良好" if score >= 70 else "中等" if score >= 60 else "待提升"

    return f"""# {name} 职业规划报告

## 目标岗位：{job}

### 匹配度评估：{score} 分（{level}）

### 核心优势
{', '.join(cfg['skills'])}

### 差距分析
{gap_text}

### 提升建议
{sug_text}

### 总结
{name} 同学当前与{job}岗位的匹配度为 {score} 分，综合评级为{level}。
建议重点关注差距项的补强，同时发挥现有技能优势，通过项目实践和实习积累提升整体竞争力。
"""


if __name__ == "__main__":
    print("Seeding teacher dashboard data...\n")
    seed()
