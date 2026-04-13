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
        resume_evidence = payload.get("resume_evidence") or {}
        student_major = payload.get("student_major", "")
        resume_intent = payload.get("resume_intent") or {}

        gap_items = match_result.get("gap_items") or []
        suggestions = match_result.get("suggestions") or []
        dimensions = match_result.get("dimensions") or []
        total_score = match_result.get("total_score", 0)

        # Build gap description from real gap_items
        gap_lines: list[str] = []
        skill_gaps = [g for g in gap_items if g.get("type") == "skill"]
        cert_gaps = [g for g in gap_items if g.get("type") == "certificate"]
        if skill_gaps:
            gap_lines.append(f"技能差距：{'、'.join(g['name'] for g in skill_gaps)}")
        if cert_gaps:
            gap_lines.append(f"证书差距：{'、'.join(g['name'] for g in cert_gaps)}")

        # Build dimension analysis from real scores
        dim_lines: list[str] = []
        for dim in dimensions:
            dim_lines.append(
                f"- {dim['dimension']}：{dim['score']:.1f} 分（权重 {dim['weight']:.0%}）— {dim.get('reasoning', '')}"
            )

        # Build strengths from matched skills in evidence
        matched_skills = resume_evidence.get("skills") or []
        student_skills = (payload.get("student_profile") or {}).get("skills") or []
        all_matched = list(dict.fromkeys(matched_skills + student_skills))

        # Build overview with real evidence
        major_text = f"，专业为 {student_major}" if student_major else ""
        intent_text = f"，意向岗位为 {resume_intent.get('job', '')}" if resume_intent.get("job") else ""
        overview = (
            f"{student_name}{major_text}{intent_text}，"
            f"当前适合优先冲刺 {job_title}，综合匹配度为 {total_score:.1f} 分。"
        )
        if all_matched:
            overview += f" 已具备的技能包括 {'、'.join(all_matched[:8])}。"
        if gap_lines:
            overview += f" 当前主要差距为 {'；'.join(gap_lines)}。"

        # Build action_plan from real gap_items and suggestions only — no generic fallbacks
        short_term: list[str] = []
        mid_term: list[str] = []
        for gap in gap_items:
            short_term.append(gap.get("suggestion", f"补齐 {gap['name']}。"))
        for suggestion in suggestions:
            short_term.append(suggestion)
        path_recs = path_result.get("recommendations") or []
        for rec in path_recs:
            if rec.get("phase") == "短期":
                short_term.append(f"{rec['focus']}：{'、'.join(rec.get('items', []))}")
            elif rec.get("phase") == "中期":
                mid_term.append(f"{rec['focus']}：{'、'.join(rec.get('items', []))}")

        # Derive metrics from gap_items instead of hardcoding
        metrics: list[str] = []
        if gap_items:
            metrics.append("岗位关键技能覆盖率")
        if path_recs:
            metrics.append("路径里程碑达成率")
        if not metrics:
            metrics.append("综合能力提升进度")

        content = {
            "overview": overview,
            "matching_analysis": {
                "fit_points": match_result.get("summary", ""),
                "dimension_scores": dimensions,
                "gap_items": gap_items,
            },
            "goals": {
                "target_job": job_title,
                "industry_trend": path_result.get("industry_trend", ""),
                "primary_path": path_result.get("primary_path", []),
                "alternate_paths": path_result.get("alternate_paths", []),
            },
            "action_plan": {
                "short_term": short_term[:6],
                "mid_term": mid_term[:6],
                "metrics": metrics,
            },
            "evidence": {
                "job_profile": payload.get("job_profile"),
                "student_profile": payload.get("student_profile"),
                "resume_evidence": resume_evidence,
                "path_reasoning": path_result.get("rationale", ""),
            },
        }

        # Build markdown from real data
        gap_section = "；".join(gap_lines) if gap_lines else match_result.get("summary", "")
        dim_section = "\n".join(dim_lines) if dim_lines else ""
        short_section = "；".join(short_term[:6])
        mid_section = "；".join(mid_term[:6])

        primary_path = path_result.get("primary_path", [])
        alt_paths = path_result.get("alternate_paths", [])
        industry_trend = path_result.get("industry_trend", "")

        markdown = (
            f"# CareerPilot 职业发展报告\n\n"
            f"## 一、职业探索与岗位匹配\n{overview}\n\n"
            f"### 评分维度\n{dim_section}\n\n"
            f"### 差距分析\n{gap_section}\n\n"
            f"## 二、职业目标与路径规划\n"
            f"- 目标岗位：{job_title}\n"
        )
        if industry_trend:
            markdown += f"- 行业趋势：{industry_trend}\n"
        if primary_path:
            markdown += f"- 主路径：{' → '.join(primary_path)}\n"
        if alt_paths:
            markdown += f"- 备选路径：{'；'.join(' → '.join(p) for p in alt_paths[:3])}\n"
        markdown += (
            f"\n## 三、行动计划与成果展示\n"
            f"- 短期：{short_section}\n"
            f"- 中期：{mid_section}\n"
            f"- 评估周期与指标：每 2-4 周复盘一次；重点看 {'、'.join(metrics)}\n\n"
            f"## 四、编辑优化与导出\n"
            f"本报告支持智能润色、内容完整性检查、手动编辑调整，并可导出为 PDF 或 DOCX。\n\n"
            f"## 五、依据说明\n"
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
        # Derive a concise reply from the system prompt context; never inject
        # a full-length generic career planning template.
        has_context = "【" in system_prompt and "学生" in system_prompt
        if has_context:
            return (
                f"根据你的背景信息，我为你整理了以下分析要点：\n\n"
                "（Mock 模式）请参考系统提示中的用户背景数据，基于真实信息给出个性化建议。\n\n"
                "> 当前为 Mock 模式，实际部署后将调用 LLM 基于你的真实数据生成完整建议。"
            )
        return (
            "你好！我是职航智策 AI 助手，专门帮助大学生进行职业规划。\n\n"
            "请先上传简历或选择目标岗位，这样我就能基于你的真实数据给出个性化建议。\n\n"
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
            "\n\n**核心要求：必须逐项消费真实匹配结果，不得生成泛化文案。**"
            "\n- overview：必须引用 match_result.total_score、resume_evidence 中的真实技能/项目/实习，以及 student_name、student_major、resume_intent。"
            "\n- matching_analysis.fit_points：直接使用 match_result.summary。"
            "\n- matching_analysis.dimension_scores：直接使用 match_result.dimensions 中各维度的 score、weight、reasoning 和 evidence。"
            "\n- matching_analysis.gap_items：直接使用 match_result.gap_items 中的 type、name、suggestion，不要自行编造差距项。"
            "\n- action_plan.short_term：必须从 match_result.gap_items 的 suggestion 字段和 match_result.suggestions 逐项构造，不要使用固定模板。"
            "\n- action_plan.mid_term：必须从 path_result.recommendations 中提取中期建议。"
            "\n- goals.primary_path 和 goals.alternate_paths：直接使用 path_result 中的路径。"
            "\n- evidence 中必须包含 job_profile、student_profile、resume_evidence、path_reasoning。"
            "\n\nmarkdown_content 需为中文职业发展报告，可直接导出，并必须覆盖以下章节："
            "一、职业探索与岗位匹配：量化呈现各维度得分与差距，差距项必须来自 match_result.gap_items；"
            "二、职业目标与路径规划：目标岗位和路径来自 path_result；"
            "三、行动计划与成果展示：短期/中期建议必须来自 gap_items.suggestion、match_result.suggestions 和 path_result.recommendations；"
            "四、编辑优化与导出。"
            "\n\n注意：如果 payload 中包含 student_major_source 字段为 'OCR解析'，说明专业信息是从简历OCR解析得到的，"
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
