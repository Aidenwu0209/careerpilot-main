from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobProfile, PathRecommendation, StudentProfile
from app.services.paths.graph_query_service import GraphQueryService

logger = logging.getLogger(__name__)


TRANSITION_FALLBACKS: dict[str, list[list[str]]] = {
    "AI 算法工程师": [
        ["AI 算法工程师", "数据工程师"],
        ["AI 算法工程师", "后端开发工程师"],
        ["AI 算法工程师", "数据分析师"],
        ["AI 算法工程师", "AI 产品经理"],
    ],
    "数据工程师": [
        ["数据工程师", "AI 算法工程师"],
        ["数据工程师", "数据分析师"],
        ["数据工程师", "后端开发工程师"],
    ],
    "数据分析师": [
        ["数据分析师", "数据产品经理"],
        ["数据分析师", "AI 算法工程师"],
        ["数据分析师", "产品经理"],
    ],
    "后端开发工程师": [
        ["后端开发工程师", "AI 算法工程师"],
        ["后端开发工程师", "数据工程师"],
        ["后端开发工程师", "全栈工程师"],
    ],
    "前端开发工程师": [
        ["前端开发工程师", "全栈工程师"],
        ["前端开发工程师", "产品经理"],
        ["前端开发工程师", "UI/UX 设计师"],
    ],
    "全栈工程师": [
        ["全栈工程师", "后端开发工程师"],
        ["全栈工程师", "前端架构师"],
        ["全栈工程师", "产品经理"],
    ],
    "产品经理": [
        ["产品经理", "数据产品经理"],
        ["产品经理", "项目经理"],
        ["产品经理", "运营专家"],
    ],
    "UI/UX 设计师": [
        ["UI/UX 设计师", "产品经理"],
        ["UI/UX 设计师", "数据产品经理"],
        ["UI/UX 设计师", "前端开发工程师"],
    ],
    "测试工程师": [
        ["测试工程师", "测试开发工程师"],
        ["测试工程师", "产品经理"],
        ["测试工程师", "数据分析师"],
    ],
    "测试开发工程师": [
        ["测试开发工程师", "后端开发工程师"],
        ["测试开发工程师", "运维工程师"],
        ["测试开发工程师", "全栈工程师"],
    ],
}


def _unique_paths(paths: list[list[str]]) -> list[list[str]]:
    seen: set[str] = set()
    result: list[list[str]] = []
    for path in paths:
        normalized = [item for item in path if item]
        key = "->".join(normalized)
        if len(normalized) >= 2 and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _job_info(title: str, profiles_by_title: dict[str, JobProfile]) -> dict:
    profile = profiles_by_title.get(title)
    return {
        "title": title,
        "description": profile.summary if profile and profile.summary else f"{title} 相关岗位，需结合业务场景持续积累项目经验。",
        "skills": (profile.skill_requirements if profile else [])[:6],
    }


class CareerPathService:
    def __init__(self, graph_query_service: GraphQueryService) -> None:
        self.graph_query_service = graph_query_service

    async def plan_path(self, db: Session, student_id: int, job_code: str) -> dict:
        try:
            student_profile = db.scalar(select(StudentProfile).where(StudentProfile.student_id == student_id))
            job_profile = db.scalar(select(JobProfile).where(JobProfile.job_code == job_code))
            if not student_profile or not job_profile:
                raise ValueError("路径规划缺少学生画像或岗位画像")
            graph = await self.graph_query_service.query_job(job_code)
            primary_path = graph["promotion_paths"][0] if graph["promotion_paths"] else [job_profile.title]
            all_profiles = list(db.scalars(select(JobProfile)).all())
            profiles_by_title: dict[str, JobProfile] = {}
            for profile in all_profiles:
                profiles_by_title.setdefault(profile.title, profile)

            alternate_paths = self._build_transition_paths(graph, job_profile.title)
            vertical_graph = self._build_vertical_graph(graph, primary_path, profiles_by_title)
            transition_graph = self._build_transition_graph(graph, job_profile.title, alternate_paths, profiles_by_title)
            gaps = [
                {"stage": "当前岗位", "missing_skills": graph["adjacent_skill_gaps"].get(path[-1], [])}
                for path in alternate_paths
            ]
            recommendations = [
                {
                    "phase": "短期",
                    "focus": "补齐目标岗位高频技能与证书",
                    "items": job_profile.skill_requirements[:3],
                },
                {
                    "phase": "中期",
                    "focus": "通过实习/项目验证路径可行性",
                    "items": ["实习投递", "竞赛项目", "阶段复盘"],
                },
            ]
            rationale = "基于岗位图谱的晋升链路和转岗链路，结合学生当前技能覆盖情况生成主路径与备选路径。"
            existing = db.scalar(
                select(PathRecommendation)
                .where(PathRecommendation.student_id == student_id)
                .where(PathRecommendation.target_job_code == job_code)
            )
            if not existing:
                existing = PathRecommendation(student_id=student_id, target_job_code=job_code)
                db.add(existing)
                db.flush()
            existing.primary_path_json = primary_path
            existing.alternate_paths_json = alternate_paths
            existing.gaps_json = gaps
            existing.recommendations_json = recommendations
            db.commit()
            return {
                "student_id": student_id,
                "target_job_code": job_code,
                "primary_path": primary_path,
                "alternate_paths": alternate_paths,
                "vertical_graph": vertical_graph,
                "transition_graph": transition_graph,
                "gaps": gaps,
                "recommendations": recommendations,
                "rationale": rationale,
            }
        except ValueError as e:
            logger.error(f"ValueError in plan_path for student {student_id}, job {job_code}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in plan_path for student {student_id}, job {job_code}: {str(e)}")
            raise ValueError(f"Failed to plan career path: {str(e)}") from e

    def _build_vertical_graph(self, graph: dict, primary_path: list[str], profiles_by_title: dict[str, JobProfile]) -> dict:
        promotion_paths = _unique_paths(graph.get("promotion_paths", []) or [primary_path])
        nodes = []
        for idx, title in enumerate(primary_path):
            info = _job_info(title, profiles_by_title)
            nodes.append({
                **info,
                "level": idx + 1,
                "stage": "当前目标" if idx == 0 else ("中期晋升" if idx == 1 else "长期发展"),
            })
        edges = [
            {
                "from": primary_path[idx],
                "to": primary_path[idx + 1],
                "relation": "晋升",
                "description": f"从 {primary_path[idx]} 晋升到 {primary_path[idx + 1]}，需要沉淀项目成果和团队协作能力。",
            }
            for idx in range(len(primary_path) - 1)
        ]
        return {
            "title": graph.get("title", primary_path[0] if primary_path else ""),
            "description": graph.get("description") or _job_info(primary_path[0], profiles_by_title)["description"],
            "nodes": nodes,
            "edges": edges,
            "promotion_paths": promotion_paths,
            "vertical_paths": graph.get("vertical_paths", []),
        }

    def _build_transition_paths(self, graph: dict, target_title: str) -> list[list[str]]:
        paths = _unique_paths(graph.get("transition_paths", []) + TRANSITION_FALLBACKS.get(target_title, []))
        for cluster in graph.get("transition_clusters", []):
            paths.extend(_unique_paths(cluster.get("related_paths", [])))
        for related_title in [target_title, "数据工程师", "数据分析师", "后端开发工程师", "全栈工程师", "产品经理", "UI/UX 设计师", "测试开发工程师"]:
            paths.extend(TRANSITION_FALLBACKS.get(related_title, []))
        return _unique_paths(paths)

    def _build_transition_graph(
        self,
        graph: dict,
        target_title: str,
        paths: list[list[str]],
        profiles_by_title: dict[str, JobProfile],
    ) -> dict:
        role_order: list[str] = [target_title]
        for path in paths:
            for title in path:
                if title not in role_order:
                    role_order.append(title)

        role_order = role_order[:8]
        role_paths = []
        for title in role_order:
            title_paths = [path for path in paths if path[0] == title or title in path]
            title_paths.extend(TRANSITION_FALLBACKS.get(title, []))
            unique = _unique_paths(title_paths)
            if len(unique) < 2:
                unique.extend(_unique_paths([[title, target_title], [title, "数据产品经理"]]))
            unique = [path for path in _unique_paths(unique) if path[0] == title or title in path][:3]
            if len(unique) < 2:
                continue
            role_paths.append({
                **_job_info(title, profiles_by_title),
                "paths": [
                    {
                        "steps": path,
                        "relation": "换岗",
                        "description": f"{path[0]} 可通过补齐 {path[-1]} 的核心技能完成转换。",
                        "skill_bridge": _job_info(path[-1], profiles_by_title)["skills"][:4],
                    }
                    for path in unique[:3]
                ],
            })

        if len(role_paths) < 5:
            for title in TRANSITION_FALLBACKS:
                if any(item["title"] == title for item in role_paths):
                    continue
                unique = _unique_paths(TRANSITION_FALLBACKS[title])
                role_paths.append({
                    **_job_info(title, profiles_by_title),
                    "paths": [
                        {
                            "steps": path,
                            "relation": "换岗",
                            "description": f"{path[0]} 可向 {path[-1]} 转换，重点补齐目标岗位技能。",
                            "skill_bridge": _job_info(path[-1], profiles_by_title)["skills"][:4],
                        }
                        for path in unique[:3]
                    ],
                })
                if len(role_paths) >= 5:
                    break

        nodes = [_job_info(title, profiles_by_title) for title in role_order]
        edges = [
            {"from": path[0], "to": path[-1], "relation": "换岗", "steps": path}
            for path in paths[:20]
        ]
        return {
            "target": target_title,
            "nodes": nodes,
            "edges": edges,
            "role_paths": role_paths[:8],
            "clusters": graph.get("transition_clusters", []),
        }
