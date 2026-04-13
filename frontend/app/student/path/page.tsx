"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SectionCard } from "@/components/SectionCard";
import { getStudentSession, getPathPlan, getPathResult, type PathPlan } from "@/lib/api";

type VerticalNode = {
  title: string;
  description?: string;
  skills?: string[];
  level?: number;
  stage?: string;
};

type TransitionRole = {
  title: string;
  description?: string;
  skills?: string[];
  paths?: Array<{
    steps: string[];
    relation?: string;
    description?: string;
    skill_bridge?: string[];
  }>;
};

export default function StudentPathPage() {
  const searchParams = useSearchParams();
  const historyId = searchParams.get("history");
  const [plan, setPlan] = useState<PathPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [isHistoricalView, setIsHistoricalView] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        if (historyId && historyId.startsWith("path-")) {
          const pathId = parseInt(historyId.replace("path-", ""), 10);
          if (!Number.isNaN(pathId)) {
            setIsHistoricalView(true);
            setPlan(await getPathResult(pathId));
            setLoading(false);
            return;
          }
        }

        const sess = await getStudentSession();
        if (!sess.student_id || !sess.suggested_job_code) {
          setLoading(false);
          return;
        }
        setPlan(await getPathPlan(sess.student_id, sess.suggested_job_code));
      } catch {
      } finally {
        setLoading(false);
      }
    })();
  }, [historyId]);

  const verticalNodes = (plan?.vertical_graph?.nodes ?? []) as VerticalNode[];
  const transitionRoles = (plan?.transition_graph?.role_paths ?? []) as TransitionRole[];
  const primaryPath = plan?.primary_path ?? [];
  const alternatePaths = plan?.alternate_paths ?? [];
  const displayedVerticalNodes: VerticalNode[] = verticalNodes.length
    ? verticalNodes
    : primaryPath.map((title, index) => ({ title, level: index + 1 }));

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>职业路径规划</h1>
          <p style={{ margin: "6px 0 0", color: "var(--subtle)", fontSize: "0.875rem" }}>
            垂直晋升路径与相关岗位换岗路径图谱
          </p>
          {isHistoricalView && (
            <p style={{ fontSize: "0.875rem", color: "#b45309", margin: "4px 0 0" }}>正在查看历史数据</p>
          )}
        </div>
        <Link href="/student" className="btn-secondary" style={{ textDecoration: "none", padding: "10px 14px", fontSize: "0.875rem" }}>
          返回问答页
        </Link>
      </div>

      {loading ? (
        <SectionCard title="加载中">
          <p style={{ textAlign: "center", padding: "40px", color: "#888" }}>加载中...</p>
        </SectionCard>
      ) : (
        <>
          <SectionCard title="垂直岗位图谱">
            <p style={{ color: "var(--subtle)", margin: "0 0 20px", lineHeight: 1.7 }}>
              {plan?.vertical_graph?.description || plan?.rationale || "基于岗位图谱生成晋升链路。"}
            </p>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {displayedVerticalNodes.map((node, index, arr) => {
                const isTarget = node.stage === "当前目标" || index === 0;
                return (
                  <div key={`${node.title}-${index}`} style={{ display: "flex", gap: 16 }}>
                    {/* Timeline rail */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 28, flexShrink: 0 }}>
                      <div
                        style={{
                          width: isTarget ? 14 : 10,
                          height: isTarget ? 14 : 10,
                          borderRadius: "50%",
                          background: isTarget ? "#0f74da" : "#fff",
                          border: `${isTarget ? 3 : 2}px solid ${isTarget ? "#0f74da" : "#c1cdd9"}`,
                          flexShrink: 0,
                          marginTop: 20,
                          boxShadow: isTarget ? "0 0 0 3px rgba(15,116,218,0.18)" : "none",
                        }}
                      />
                      {index < arr.length - 1 && (
                        <div style={{ width: 2, flex: 1, background: "#dde5ed", minHeight: 16 }} />
                      )}
                    </div>
                    {/* Node card */}
                    <div
                      style={{
                        flex: 1,
                        border: isTarget ? "2px solid #0f74da" : "1px solid rgba(15,116,218,0.16)",
                        borderRadius: 8,
                        padding: 16,
                        background: isTarget ? "#eef6ff" : "#fff",
                        marginBottom: 12,
                        boxShadow: isTarget ? "0 2px 8px rgba(15,116,218,0.12)" : "none",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 10, alignItems: "center" }}>
                        <span style={{ color: "#0f74da", fontWeight: 700, fontSize: "0.8125rem" }}>L{node.level ?? index + 1}</span>
                        {node.stage && (
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: 6,
                              background: isTarget ? "#0f74da" : "#f0fdfa",
                              color: isTarget ? "#fff" : "#0f766e",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                            }}
                          >
                            {node.stage}
                          </span>
                        )}
                      </div>
                      <h3 style={{ margin: "0 0 8px", fontSize: "1rem" }}>{node.title}</h3>
                      <p style={{ margin: "0 0 12px", color: "var(--subtle)", fontSize: "0.8125rem", lineHeight: 1.6 }}>{node.description || "围绕岗位要求持续沉淀项目成果。"}</p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(node.skills ?? []).slice(0, 4).map((skill) => (
                          <span key={skill} style={{ padding: "4px 8px", borderRadius: 8, background: "#eef6ff", color: "#0f4f9a", fontSize: "0.75rem", fontWeight: 600 }}>{skill}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {(plan?.vertical_graph?.promotion_paths ?? []).length > 1 && (
              <div style={{ marginTop: 18 }}>
                <h3 style={{ margin: "0 0 10px", fontSize: "0.9375rem" }}>其他晋升链路</h3>
                <div style={{ display: "grid", gap: 8 }}>
                  {(plan?.vertical_graph?.promotion_paths ?? []).map((path: string[]) => (
                    <div key={path.join("-")} style={{ padding: "10px 12px", borderRadius: 8, background: "#f8fafc", color: "var(--ink)" }}>
                      {path.join(" → ")}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </SectionCard>

          <SectionCard title="换岗路径图谱">
            <p style={{ color: "var(--subtle)", margin: "0 0 20px", lineHeight: 1.7 }}>
              以 <strong style={{ color: "var(--ink)" }}>{plan?.transition_graph?.target || "当前岗位"}</strong> 为中心，已关联{" "}
              {transitionRoles.length || 0} 个相关岗位，每个岗位提供多条换岗路径及技能桥接点。
            </p>
            {transitionRoles.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {transitionRoles.map((role, roleIdx) => {
                  const isTargetRole = role.title === plan?.transition_graph?.target;
                  return (
                    <div
                      key={role.title}
                      style={{
                        display: "flex",
                        gap: 16,
                        alignItems: "flex-start",
                      }}
                    >
                      {/* Role node */}
                      <div
                        style={{
                          width: 140,
                          flexShrink: 0,
                          padding: "12px 14px",
                          borderRadius: 8,
                          border: isTargetRole ? "2px solid #0f74da" : "1px solid rgba(0,0,0,0.08)",
                          background: isTargetRole ? "#eef6ff" : "#fff",
                          boxShadow: isTargetRole ? "0 2px 8px rgba(15,116,218,0.12)" : "0 1px 3px rgba(0,0,0,0.04)",
                          textAlign: "center",
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: "50%",
                            background: isTargetRole ? "#0f74da" : "#f0f4f8",
                            color: isTargetRole ? "#fff" : "#64748b",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            margin: "0 auto 8px",
                            fontSize: "0.75rem",
                            fontWeight: 700,
                          }}
                        >
                          {roleIdx + 1}
                        </div>
                        <h3 style={{ margin: "0 0 4px", fontSize: "0.875rem", fontWeight: 700 }}>{role.title}</h3>
                        <p style={{ margin: 0, color: "var(--subtle)", fontSize: "0.75rem", lineHeight: 1.4 }}>{role.description}</p>
                        {(role.skills?.length ?? 0) > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, justifyContent: "center", marginTop: 8 }}>
                            {(role.skills ?? []).slice(0, 3).map((skill) => (
                              <span
                                key={skill}
                                style={{
                                  padding: "2px 6px",
                                  borderRadius: 6,
                                  background: isTargetRole ? "#dbeafe" : "#f0f4f8",
                                  color: isTargetRole ? "#1d4ed8" : "#64748b",
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                }}
                              >
                                {skill}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Connector + paths */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                          <div style={{ width: 24, height: 2, background: isTargetRole ? "#0f74da" : "#dde5ed" }} />
                          <span style={{ fontSize: "0.75rem", color: "var(--subtle)", fontWeight: 600 }}>
                            {role.paths?.length || 0} 条换岗路径
                          </span>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                          {(role.paths ?? []).slice(0, 3).map((path, pathIdx) => (
                            <div
                              key={path.steps.join("-")}
                              style={{
                                padding: 14,
                                borderRadius: 8,
                                background: "#f8fafc",
                                border: "1px solid rgba(0,0,0,0.04)",
                              }}
                            >
                              {/* Step flow */}
                              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                                {path.steps.map((step, stepIdx) => (
                                  <span key={step} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <span
                                      style={{
                                        padding: "3px 10px",
                                        borderRadius: 6,
                                        background: isTargetRole && stepIdx === 0 ? "#0f74da" : "#fff",
                                        color: isTargetRole && stepIdx === 0 ? "#fff" : "var(--ink)",
                                        fontSize: "0.8125rem",
                                        fontWeight: 600,
                                        border: isTargetRole && stepIdx === 0 ? "none" : "1px solid #e2e8f0",
                                      }}
                                    >
                                      {step}
                                    </span>
                                    {stepIdx < path.steps.length - 1 && (
                                      <span style={{ color: "#94a3b8", fontSize: "0.75rem" }}>→</span>
                                    )}
                                  </span>
                                ))}
                              </div>

                              {/* Description */}
                              <p style={{ margin: "0 0 8px", color: "var(--subtle)", fontSize: "0.8125rem", lineHeight: 1.6 }}>
                                {path.description || `${path.steps[0]} 可通过补齐 ${path.steps[path.steps.length - 1]} 的核心技能完成转换。`}
                              </p>

                              {/* Skill bridge */}
                              {(path.skill_bridge ?? []).length > 0 && (
                                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                  <span style={{ fontSize: "0.75rem", color: "#8a4b00", fontWeight: 600 }}>技能桥接：</span>
                                  {(path.skill_bridge ?? []).map((skill) => (
                                    <span
                                      key={skill}
                                      style={{
                                        padding: "3px 8px",
                                        borderRadius: 6,
                                        background: "#fff4e5",
                                        color: "#8a4b00",
                                        fontSize: "0.75rem",
                                        fontWeight: 600,
                                      }}
                                    >
                                      {skill}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "32px 0", color: "#888" }}>
                <p style={{ margin: 0 }}>暂无换岗路径数据</p>
                {alternatePaths.length > 0 && (
                  <ul className="plain-list" style={{ textAlign: "left", maxWidth: 480, margin: "12px auto 0" }}>
                    {alternatePaths.map((path: string[]) => (
                      <li key={path.join("-")}>{path.join(" → ")}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </SectionCard>

          <SectionCard title="路径依据">
            <p style={{ lineHeight: 1.8 }}>{plan?.rationale || "基于岗位图谱的晋升链路和转岗链路，结合学生当前技能覆盖情况生成主路径与备选路径。"}</p>
          </SectionCard>
        </>
      )}
    </div>
  );
}
