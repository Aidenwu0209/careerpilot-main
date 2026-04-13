"""Unified job graph data model for career path planning.

Provides typed Pydantic schemas for vertical_graph and transition_graph
so that both the current page and history replay use the same structure.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Vertical Graph – 纵向晋升图谱
# ---------------------------------------------------------------------------

class VerticalGraphNode(BaseModel):
    title: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    level: int = 1
    stage: str = ""


class VerticalGraphEdge(BaseModel):
    model_config = {"populate_by_name": True}

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    relation: str = ""
    description: str = ""


class VerticalGraph(BaseModel):
    title: str = ""
    description: str = ""
    nodes: list[VerticalGraphNode] = Field(default_factory=list)
    edges: list[VerticalGraphEdge] = Field(default_factory=list)
    promotion_paths: list[list[str]] = Field(default_factory=list)
    vertical_paths: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Transition Graph – 换岗路径图谱
# ---------------------------------------------------------------------------

class TransitionPath(BaseModel):
    steps: list[str] = Field(default_factory=list)
    relation: str = ""
    description: str = ""
    skill_bridge: list[str] = Field(default_factory=list)


class TransitionRole(BaseModel):
    title: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    paths: list[TransitionPath] = Field(default_factory=list)


class TransitionGraph(BaseModel):
    target: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    role_paths: list[TransitionRole] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Career Path Response – 统一返回结构
# ---------------------------------------------------------------------------

class CareerPathResponse(BaseModel):
    student_id: Optional[int] = None
    target_job_code: str = ""
    primary_path: list[str] = Field(default_factory=list)
    alternate_paths: list[list[str]] = Field(default_factory=list)
    vertical_graph: VerticalGraph = Field(default_factory=VerticalGraph)
    transition_graph: TransitionGraph = Field(default_factory=TransitionGraph)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""
