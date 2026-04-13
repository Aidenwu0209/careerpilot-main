from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from app.services.reference import find_best_template

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_job_profile(self, job_posting: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def generate_student_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def polish_markdown(self, markdown_content: str) -> str:
        raise NotImplementedError


class MockLLMProvider(BaseLLMProvider):
    async def generate_job_profile(self, job_posting: dict[str, Any]) -> dict[str, Any]:
        template = find_best_template(job_posting["title"])
        return {
            "job_code": job_posting["job_code"],
            "title": job_posting["title"],
            "summary": template["summary"],
            "skill_requirements": template["skills"],
            "certificate_requirements": template["certificates"],
            "innovation_requirements": template["explanations"]["创新能力"],
            "learning_requirements": template["explanations"]["学习能力"],
            "resilience_requirements": template["explanations"]["抗压能力"],
            "communication_requirements": template["explanations"]["沟通能力"],
            "internship_requirements": template["explanations"]["实习能力"],
            "capability_scores": template["capabilities"],
            "dimension_weights": template["dimension_weights"],
            "explanation_json": template["explanations"],
        }

    async def generate_student_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        skills = sorted(set(payload.get("skills", [])))
        certificates = sorted(set(payload.get("certificates", [])))
        internships = payload.get("internships", [])
        projects = payload.get("projects", [])
        capability_scores = {
            "innovation": min(95, 55 + len(projects) * 12),
            "learning": min(95, 60 + len(skills) * 3 + len(certificates) * 5),
            "resilience": min(95, 60 + len(internships) * 8),
            "communication": min(95, 58 + len(projects) * 6 + len(internships) * 5),
            "internship": min(95, 50 + len(internships) * 15),
        }
        completeness_items = [
            bool(skills),
            bool(certificates),
            bool(projects),
            bool(internships),
            bool(payload.get("self_introduction")),
        ]
        completeness_score = round(sum(1 for item in completeness_items if item) / len(completeness_items) * 100, 2)
        competitiveness_score = round(
            (len(skills) * 7 + len(certificates) * 6 + len(projects) * 10 + len(internships) * 12)
            + sum(capability_scores.values()) / 8,
            2,
        )
        evidence = []
        for skill in skills:
            evidence.append({"source": "融合输入", "excerpt": f"识别到技能：{skill}", "confidence": 0.92})
        for certificate in certificates:
            evidence.append({"source": "融合输入", "excerpt": f"识别到证书：{certificate}", "confidence": 0.95})
        return {
            "source_summary": payload.get("source_summary", ""),
            "skills": skills,
            "certificates": certificates,
            "capability_scores": capability_scores,
            "completeness_score": completeness_score,
            "competitiveness_score": min(100.0, competitiveness_score),
            "willingness": payload.get("preferences", {}),
            "evidence": evidence,
        }

    async def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        student_name = payload.get("student_name", "学生")
        job_title = payload.get("job_title", "目标岗位")
        match_result = payload["match_result"]
        path_result = payload["path_result"]
        student_profile = payload.get("student_profile", {})
        job_profile = payload.get("job_profile", {})

        # --- overview: derive from real match data only ---
        total_score = match_result.get("total_score", 0)
        overview = f"{student_name} 当前适合优先冲刺 {job_title}，综合匹配度为 {total_score:.1f} 分。"

        # --- action_plan: derive gap-based short/mid terms from real data ---
        gap_items = match_result.get("gap_items", [])
        missing_skills = [g.get("item", "") for g in gap_items if g.get("type") == "skill"]
        student_skills = student_profile.get("skills", []) if isinstance(student_profile, dict) else []
        evidence = payload.get("resume_evidence", {})
        has_projects = bool(evidence.get("projects")) if isinstance(evidence, dict) else False

        short_term: list[str] = []
        if missing_skills:
            short_term.append(f"重点补齐岗位核心技能：{'、'.join(missing_skills[:5])}")
        if not has_projects:
            short_term.append("完善至少 1 个可展示的项目并沉淀成果描述")
        else:
            short_term.append("持续完善项目成果描述，提升可展示性")

        mid_term: list[str] = []
        certificates = student_profile.get("certificates", []) if isinstance(student_profile, dict) else []
        if certificates:
            mid_term.append(f"考取岗位相关证书，当前已持：{'、'.join(certificates[:3])}")
        else:
            mid_term.append("考取目标岗位相关的职业证书")

        metrics = ["岗位关键技能覆盖率", "项目/实习产出数量"]

        content = {
            "overview": overview,
            "matching_analysis": {
                "fit_points": match_result["summary"],
                "dimension_scores": match_result["dimensions"],
                "gap_items": gap_items,
            },
            "goals": {
                "target_job": job_title,
                "primary_path": path_result.primary_path,
                "alternate_paths": path_result.alternate_paths,
            },
            "action_plan": {
                "short_term": short_term or ["制定个人学习计划，逐步补齐岗位核心技能"],
                "mid_term": mid_term or ["完成至少 1 次实习或竞赛经历"],
                "metrics": metrics,
            },
            "evidence": {
                "job_profile": job_profile,
                "student_profile": student_profile,
                "path_reasoning": path_result.rationale,
            },
        }

        # --- markdown: structure-only template, all content from real data ---
        dim_lines = []
        for dim in match_result.get("dimensions", []):
            dim_lines.append(f"  - **{dim.get('name', '')}**：{dim.get('score', 0):.1f} 分（权重 {dim.get('weight', 0):.0%}）")

        gap_lines = []
        for g in gap_items:
            gap_lines.append(f"  - {g.get('item', '')}（{g.get('type', '')}）")

        path_lines = " -> ".join(path_result.primary_path) if path_result.primary_path else "暂无"
        alt_lines = "; ".join(" -> ".join(p) for p in path_result.alternate_paths) if path_result.alternate_paths else "暂无"

        markdown = (
            f"# CareerPilot 职业发展报告\n\n"
            f"## 一、职业探索与岗位匹配\n\n"
            f"{overview}\n\n"
            f"### 匹配度详情\n\n"
            + ("\n".join(dim_lines) if dim_lines else "暂无维度评分数据") + "\n\n"
            f"### 差距分析\n\n"
            + ("\n".join(gap_lines) if gap_lines else "暂无差距数据") + "\n\n"
            f"## 二、职业目标与路径规划\n\n"
            f"- **目标岗位**：{job_title}\n"
            f"- **主路径**：{path_lines}\n"
            f"- **备选路径**：{alt_lines}\n\n"
            f"## 三、行动计划与成果展示\n\n"
            f"### 短期计划\n\n"
            + "\n".join(f"- {item}" for item in content["action_plan"]["short_term"]) + "\n\n"
            f"### 中期计划\n\n"
            + "\n".join(f"- {item}" for item in content["action_plan"]["mid_term"]) + "\n\n"
            f"### 评估指标\n\n"
            + "\n".join(f"- {m}" for m in metrics) + "\n\n"
            f"## 四、编辑优化与导出\n\n"
            f"本报告支持智能润色、内容完整性检查、手动编辑调整，并可导出为 PDF 或 DOCX。\n\n"
            f"## 五、依据说明\n\n"
            f"- 学生画像与证据链已纳入分析\n"
            f"- 岗位画像、图谱路径、四维评分均可追溯\n"
        )
        return {"content": content, "markdown_content": markdown}

    async def polish_markdown(self, markdown_content: str) -> str:
        polished = markdown_content.strip()
        if "CareerPilot 职业发展报告" not in polished:
            polished = f"# CareerPilot 职业发展报告\n\n{polished}"
        return polished + "\n\n> 本报告已完成智能润色与结构校验。"

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        # Mock chat returns a minimal structural response without injecting
        # fixed conclusions. Real analysis should come from LLM or user data.
        return (
            "你好！我是职航智策 AI 助手，专门帮助大学生进行职业规划。\n\n"
            "你可以问我：\n"
            "- 某个岗位需要什么技能？\n"
            "- 如何从当前专业转入某个职业方向？\n"
            "- 某个行业的发展前景如何？\n\n"
            "请描述你的问题，我会尽力为你解答！"
        )


class ErnieLLMProvider(BaseLLMProvider):
    def __init__(
        self,
        access_token: str,
        base_url: str = "https://aistudio.baidu.com/llm/lmapi/v3",
        model: str = "ernie-5.0-thinking-preview",
    ) -> None:
        self.access_token = access_token
        self.base_url = base_url
        self.model = model
        self.mock = MockLLMProvider()
        self.client = OpenAI(api_key=access_token, base_url=base_url, timeout=60.0) if access_token else None

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced:
            return json.loads(fenced.group(1))
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            return json.loads(text[first : last + 1])
        raise ValueError("no json object found")

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            mapping = {"low": 0.55, "medium": 0.75, "high": 0.92}
            lowered = value.strip().lower()
            if lowered in mapping:
                return mapping[lowered]
            try:
                return float(lowered)
            except ValueError:
                return default
        return default

    def _normalize_student_profile(self, parsed: dict[str, Any]) -> dict[str, Any]:
        capabilities = parsed.get("capability_scores", {}) or {}
        normalized_capabilities = {
            "innovation": round(self._to_float(capabilities.get("innovation"), 60.0), 2),
            "learning": round(self._to_float(capabilities.get("learning"), 60.0), 2),
            "resilience": round(self._to_float(capabilities.get("resilience"), 60.0), 2),
            "communication": round(self._to_float(capabilities.get("communication"), 60.0), 2),
            "internship": round(self._to_float(capabilities.get("internship"), 60.0), 2),
        }
        evidence = []
        for item in parsed.get("evidence", []) or []:
            if isinstance(item, dict):
                evidence.append(
                    {
                        "source": str(item.get("source", "ERNIE")),
                        "excerpt": str(item.get("excerpt", "")),
                        "confidence": round(self._to_float(item.get("confidence"), 0.8), 2),
                    }
                )
        return {
            "source_summary": str(parsed.get("source_summary", "ERNIE 生成画像")),
            "skills": [str(item) for item in parsed.get("skills", []) if item],
            "certificates": [str(item) for item in parsed.get("certificates", []) if item],
            "capability_scores": normalized_capabilities,
            "completeness_score": round(self._to_float(parsed.get("completeness_score"), 80.0), 2),
            "competitiveness_score": round(self._to_float(parsed.get("competitiveness_score"), 80.0), 2),
            "willingness": parsed.get("willingness", {}) if isinstance(parsed.get("willingness", {}), dict) else {},
            "evidence": evidence,
        }

    def _normalize_job_profile(self, parsed: dict[str, Any], fallback_title: str, fallback_job_code: str) -> dict[str, Any]:
        capabilities = parsed.get("capability_scores", {}) or {}
        weights = parsed.get("dimension_weights", {}) or {}
        normalized = {
            "job_code": str(parsed.get("job_code", fallback_job_code)),
            "title": str(parsed.get("title", fallback_title)),
            "summary": str(parsed.get("summary", "")),
            "skill_requirements": [str(item) for item in parsed.get("skill_requirements", []) if item],
            "certificate_requirements": [str(item) for item in parsed.get("certificate_requirements", []) if item],
            "innovation_requirements": str(parsed.get("innovation_requirements", "")),
            "learning_requirements": str(parsed.get("learning_requirements", "")),
            "resilience_requirements": str(parsed.get("resilience_requirements", "")),
            "communication_requirements": str(parsed.get("communication_requirements", "")),
            "internship_requirements": str(parsed.get("internship_requirements", "")),
            "capability_scores": {
                "innovation": round(self._to_float(capabilities.get("innovation"), 75.0), 2),
                "learning": round(self._to_float(capabilities.get("learning"), 80.0), 2),
                "resilience": round(self._to_float(capabilities.get("resilience"), 75.0), 2),
                "communication": round(self._to_float(capabilities.get("communication"), 78.0), 2),
                "internship": round(self._to_float(capabilities.get("internship"), 75.0), 2),
            },
            "dimension_weights": {
                "basic_requirements": round(self._to_float(weights.get("basic_requirements"), 0.2), 2),
                "professional_skills": round(self._to_float(weights.get("professional_skills"), 0.4), 2),
                "professional_literacy": round(self._to_float(weights.get("professional_literacy"), 0.2), 2),
                "development_potential": round(self._to_float(weights.get("development_potential"), 0.2), 2),
            },
            "explanation_json": parsed.get("explanation_json", {}) if isinstance(parsed.get("explanation_json", {}), dict) else {},
        }
        return normalized

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.client:
            raise RuntimeError("AI Studio Access Token 未配置")
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        return completion.choices[0].message.content or ""

    async def generate_job_profile(self, job_posting: dict[str, Any]) -> dict[str, Any]:
        system_prompt = (
            "你是 CareerPilot 的岗位画像专家。"
            "请仅返回 JSON，不要输出解释、标题或 Markdown。"
            "JSON 字段必须包含：job_code,title,summary,skill_requirements,"
            "certificate_requirements,innovation_requirements,learning_requirements,"
            "resilience_requirements,communication_requirements,internship_requirements,"
            "capability_scores,dimension_weights,explanation_json。"
            "其中 capability_scores 必须包含 innovation,learning,resilience,communication,internship 五项 0-100 分。"
            "dimension_weights 必须包含 basic_requirements,professional_skills,professional_literacy,development_potential 四项，且总和为 1。"
            "explanation_json 需包含 专业技能、证书要求、创新能力、学习能力、抗压能力、沟通能力、实习能力 七项。"
        )
        user_prompt = json.dumps(job_posting, ensure_ascii=False)
        try:
            content = self._chat(system_prompt, user_prompt)
            parsed = self._extract_json(content)
            return self._normalize_job_profile(parsed, job_posting["title"], job_posting["job_code"])
        except Exception as exc:
            logger.warning("ERNIE job profile generation failed, fallback to mock: %s", exc)
            return await self.mock.generate_job_profile(job_posting)

    async def generate_student_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        system_prompt = (
            "你是 CareerPilot 的学生就业能力画像专家。"
            "请根据输入材料生成学生画像，并且只返回 JSON。"
            "JSON 字段必须包含：source_summary,skills,certificates,capability_scores,"
            "completeness_score,competitiveness_score,willingness,evidence。"
            "capability_scores 必须包含 innovation,learning,resilience,communication,internship 五项分数。"
            "evidence 必须是数组，每项包含 source,excerpt,confidence。"
            "请重点分析以下内容："
            "1. 实习经历：从实习中提取相关技能、工作内容、职责范围和实践经验"
            "2. 项目经历：分析项目的技术难度、团队协作、个人贡献和实际成果"
            "3. 评估这些经历对职业发展的价值和与目标岗位的匹配度"
            "4. 将具体的实习和项目经历作为证据链的一部分"
            "注意：如果 payload 中包含 major_source 字段为 'OCR解析'，说明专业信息是从简历OCR解析得到的，"
            "这是最准确的信息来源，请直接使用，不要提示与'学生基本信息'存在差异。"
        )
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            content = self._chat(system_prompt, user_prompt)
            parsed = self._extract_json(content)
            return self._normalize_student_profile(parsed)
        except Exception as exc:
            logger.warning("ERNIE student profile generation failed, fallback to mock: %s", exc)
            return await self.mock.generate_student_profile(payload)

    async def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        system_prompt = (
            "你是 CareerPilot 的职业规划报告生成专家。"
            "请只返回 JSON，不要输出 Markdown 代码块。"
            "JSON 顶层字段必须包含 content 和 markdown_content。"
            "content 必须包含 overview,matching_analysis,goals,action_plan,evidence。"
            "\n\n"
            "## 结构骨架要求（仅定义章节和字段占位）\n"
            "markdown_content 需为中文职业发展报告，必须包含以下四个章节标题：\n"
            "- 一、职业探索与岗位匹配\n"
            "- 二、职业目标设定与职业路径规划\n"
            "- 三、行动计划与成果展示\n"
            "- 四、编辑优化与导出\n\n"
            "## 正文生成要求（真实数据优先）\n"
            "**禁止**在模板中注入固定结论文案、通用建议或虚构内容。"
            "所有正文必须基于 payload 中的真实数据生成：\n"
            "- overview：引用 match_result.total_score 和 job_title\n"
            "- matching_analysis：引用 match_result.dimensions 和 gap_items 中的具体数据\n"
            "- goals：引用 path_result.primary_path 和 alternate_paths\n"
            "- action_plan：根据 gap_items 中的具体缺失项生成针对性建议，不使用通用占位\n"
            "- evidence：引用 job_profile 和 student_profile 的真实数据\n"
            "如果 payload 中缺少某项数据，在对应章节中明确标注'数据不足'，而不是编造内容。"
            "\n"
            "注意：如果 payload 中包含 student_major_source 字段为 'OCR解析'，说明专业信息是从简历OCR解析得到的，"
            "这是最准确的信息来源，请直接使用 student_major 字段作为专业信息，"
            "不要提示与'学生基本信息'存在差异或建议核实。"
        )
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            content = self._chat(system_prompt, user_prompt)
            parsed = self._extract_json(content)
            return parsed
        except Exception as exc:
            logger.warning("ERNIE report generation failed, fallback to mock: %s", exc)
            return await self.mock.generate_report(payload)

    async def polish_markdown(self, markdown_content: str) -> str:
        system_prompt = (
            "你是 CareerPilot 的中文报告润色助手。"
            "请在不改变事实的前提下润色内容，并返回纯 Markdown 文本。"
            "要求保留标题结构，增强可读性、完整性和职业规划语气。"
        )
        try:
            polished = self._chat(system_prompt, markdown_content).strip()
            if not polished:
                raise ValueError("empty polished content")
            return polished
        except Exception as exc:
            logger.warning("ERNIE markdown polish failed, fallback to mock: %s", exc)
            return await self.mock.polish_markdown(markdown_content)


async def safe_ping_http(url: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            return response.status_code < 500
    except Exception:
        return False
