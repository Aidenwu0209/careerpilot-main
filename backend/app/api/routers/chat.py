import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session
from app.models import ChatMessageRecord, Student, StudentProfile, UploadedFile, User
from app.schemas.chat import ChatRequest, ChatResponse, GreetingResponse
from app.services.bootstrap import get_user_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_SYSTEM_PROMPT = (
    "你是职航智策（CareerPilot）的职业规划AI助手，专门帮助中国大学生分析职业方向、岗位匹配、能力评估和职业路径规划。\n"
    "请用中文回答。如果用户的问题与职业规划无关，礼貌地引导回职业话题。\n\n"
    "## 回答格式要求\n"
    "当用户请求分析、评估、规划或报告时，必须以结构化 Markdown 报告格式回复，包含以下章节：\n"
    "- # 标题（概括分析主题）\n"
    "- ## 一、综合概述（简要总结用户当前状态和核心结论）\n"
    "- ## 二、能力分析（根据用户背景，逐项分析各项能力，给出评分或等级）\n"
    "- ## 三、优势与不足（分别列出用户的优势项和待提升项）\n"
    "- ## 四、职业方向建议（推荐适合的职业方向，说明理由）\n"
    "- ## 五、行动建议（给出短期/中期/长期的具体行动计划）\n"
    "- ## 六、总结（一段总结性建议）\n\n"
    "如果用户只是简单提问（如某个岗位需要什么技能），可以简短回答，但仍然使用 Markdown 列表格式。\n"
    "禁止用一段纯文字回复。必须使用标题、列表、粗体等 Markdown 格式。"
)


def _build_user_context(db: Session, user_id: int) -> str:
    parts: list[str] = []

    student = db.scalar(select(Student).where(Student.user_id == user_id))
    if student:
        info_lines: list[str] = []
        if student.major:
            info_lines.append(f"专业：{student.major}")
        if student.grade:
            info_lines.append(f"年级：{student.grade}")
        if student.career_goal:
            info_lines.append(f"职业目标：{student.career_goal}")
        if info_lines:
            parts.append("【学生基本信息】\n" + "\n".join(info_lines))

        profile = db.scalar(
            select(StudentProfile).where(StudentProfile.student_id == student.id)
        )
        if profile:
            profile_lines: list[str] = []
            if profile.source_summary:
                profile_lines.append(f"综合评价：{profile.source_summary}")
            if profile.skills_json:
                skills = profile.skills_json if isinstance(profile.skills_json, list) else []
                if skills:
                    profile_lines.append(f"技能标签：{', '.join(str(s) for s in skills[:20])}")
            if profile.certificates_json:
                certs = profile.certificates_json if isinstance(profile.certificates_json, list) else []
                if certs:
                    profile_lines.append(f"证书：{', '.join(str(c) for c in certs[:10])}")
            if profile.capability_scores and isinstance(profile.capability_scores, dict):
                scores_text = ", ".join(
                    f"{k}: {v}" for k, v in list(profile.capability_scores.items())[:8]
                )
                if scores_text:
                    profile_lines.append(f"能力评分：{scores_text}")
            if profile.completeness_score:
                profile_lines.append(f"档案完整度：{profile.completeness_score:.0%}")
            if profile.competitiveness_score:
                profile_lines.append(f"竞争力评分：{profile.competitiveness_score:.0%}")
            if profile_lines:
                parts.append("【学生能力画像】\n" + "\n".join(profile_lines))

    files = db.scalars(
        select(UploadedFile)
        .where(UploadedFile.owner_id == user_id)
        .order_by(UploadedFile.created_at.desc())
        .limit(2)
    ).all()
    if files:
        ocr_parts: list[str] = []
        for f in files:
            meta = f.meta_json or {}
            ocr_text = meta.get("ocr", {})
            if isinstance(ocr_text, dict):
                text = ocr_text.get("text", "")
                structured = ocr_text.get("structured_json", {})
            elif isinstance(ocr_text, str):
                text = ocr_text
                structured = {}
            else:
                continue
            if not text and not structured:
                continue
            entry_lines = [f"--- 文件：{f.file_name}（{f.file_type}）---"]
            if text:
                entry_lines.append(text[:600])
            if structured:
                entry_lines.append(json.dumps(structured, ensure_ascii=False)[:600])
            ocr_parts.append("\n".join(entry_lines))
        if ocr_parts:
            parts.append("【用户上传的简历/文件 OCR 解析内容】\n" + "\n\n".join(ocr_parts))

    if not parts:
        return ""

    return (
        "以下是你正在对话的用户的相关背景信息，请在回答时参考这些内容给出个性化建议：\n\n"
        + "\n\n".join(parts)
    )


@router.get("/greeting", response_model=GreetingResponse)
def greeting(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> GreetingResponse:
    user_ctx = _build_user_context(db, current_user.id)

    recent = db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.user_id == current_user.id, ChatMessageRecord.role == "user")
        .order_by(ChatMessageRecord.created_at.desc())
        .limit(10)
    ).all()
    history_lines = [f"- {m.content[:80]}" for m in reversed(recent)] if recent else []

    student = db.scalar(select(Student).where(Student.user_id == current_user.id))

    fallback_greeting = "你好，想了解什么职业方向？"
    fallback_subline = "输入你感兴趣的岗位方向或上传简历，AI 帮你分析"

    if student and student.career_goal:
        fallback_greeting = f"你好！来聊聊{student.career_goal}方向？"
        fallback_subline = "上传简历或直接提问，AI 帮你深入分析"
    elif student and student.major:
        fallback_greeting = f"你好，{student.major}同学！想了解什么职业方向？"
        fallback_subline = "上传简历或直接提问，AI 帮你规划职业路径"

    if not user_ctx and not history_lines:
        return GreetingResponse(greeting=fallback_greeting, subline=fallback_subline)

    context_block = ""
    if user_ctx:
        context_block = f"\n\n用户背景信息：\n{user_ctx}"
    if history_lines:
        context_block += f"\n\n用户最近的聊天话题：\n" + "\n".join(history_lines)

    system_prompt = (
        "你是职航智策（CareerPilot）的职业规划AI助手。"
        "请根据用户的背景信息和历史聊天记录，生成一句个性化、简短亲切的中文问候语，引导用户开始新的职业规划对话。\n"
        "要求：\n"
        "1. 问候语不超过30个字，自然口语化\n"
        "2. 如果用户有明确的职业目标，围绕目标给出引导\n"
        "3. 如果没有明确目标，根据专业或历史话题引导\n"
        "4. 每次问候尽量不同，有新鲜感\n"
        "5. 再生成一句简短的副标题（不超过25字），提示用户可以做什么\n"
        "6. 严格按以下JSON格式返回，不要返回其他内容：\n"
        '{"greeting": "问候语", "subline": "副标题"}'
    )

    provider = get_user_llm_provider(None, current_user.id)
    try:
        raw = provider._chat(system_prompt, context_block or "新用户，暂无背景信息")
        parsed = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        greeting_text = parsed.get("greeting", fallback_greeting)
        subline_text = parsed.get("subline", fallback_subline)
        return GreetingResponse(greeting=greeting_text[:60], subline=subline_text[:50])
    except Exception as exc:
        logger.warning("Greeting generation failed for user %s: %s", current_user.id, exc)
        return GreetingResponse(greeting=fallback_greeting, subline=fallback_subline)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ChatResponse:
    user_ctx = _build_user_context(db, current_user.id)
    system_prompt = (
        "你是 CareerPilot 的职业规划助手。请用中文回答，优先给出可执行建议。"
        "默认保持简洁：除非用户明确要求完整报告，否则控制在 800 字以内。"
        "回答使用 Markdown 标题和要点列表，不要输出无关铺垫。"
    )
    if user_ctx:
        system_prompt = f"{system_prompt}\n\n{user_ctx}"

    provider = get_user_llm_provider(None, current_user.id)
    try:
        reply = provider._chat(system_prompt, payload.message)

        db.add(ChatMessageRecord(
            user_id=current_user.id,
            role="user",
            content=payload.message,
            has_context=bool(user_ctx),
        ))
        db.add(ChatMessageRecord(
            user_id=current_user.id,
            role="assistant",
            content=reply,
            has_context=bool(user_ctx),
        ))
        db.commit()

        return ChatResponse(reply=reply)
    except ValueError as exc:
        return ChatResponse(reply=f"API 认证失败：{exc}。请联系管理员检查系统 API 配置。")
    except ConnectionError:
        return ChatResponse(reply="网络连接失败，无法连接到 AI 服务，请检查网络后重试。")
    except TimeoutError:
        return ChatResponse(reply="请求超时，AI 服务响应较慢，请稍后再试。")
    except Exception as exc:
        logger.warning("Chat failed for user %s: %s", current_user.id, exc)
        return ChatResponse(reply=f"AI 模型调用失败：{exc}。请稍后再试。")
