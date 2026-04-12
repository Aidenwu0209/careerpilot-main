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
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, alignItems: "stretch" }}>
              {displayedVerticalNodes.map((node, index, arr) => (
                <div key={`${node.title}-${index}`} style={{ display: "flex", gap: 12, alignItems: "stretch" }}>
                  <div style={{ flex: 1, border: "1px solid rgba(15,116,218,0.16)", borderRadius: 8, padding: 16, background: "#fff" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
                      <span style={{ color: "#0f74da", fontWeight: 700, fontSize: "0.8125rem" }}>L{node.level ?? index + 1}</span>
                      {node.stage && <span style={{ color: "#0f766e", fontSize: "0.75rem", fontWeight: 700 }}>{node.stage}</span>}
                    </div>
                    <h3 style={{ margin: "0 0 8px", fontSize: "1rem" }}>{node.title}</h3>
                    <p style={{ margin: "0 0 12px", color: "var(--subtle)", fontSize: "0.8125rem", lineHeight: 1.6 }}>{node.description || "围绕岗位要求持续沉淀项目成果。"}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {(node.skills ?? []).slice(0, 4).map((skill) => (
                        <span key={skill} style={{ padding: "4px 8px", borderRadius: 8, background: "#eef6ff", color: "#0f4f9a", fontSize: "0.75rem", fontWeight: 600 }}>{skill}</span>
                      ))}
                    </div>
                  </div>
                  {index < arr.length - 1 && (
                    <div style={{ display: "flex", alignItems: "center", color: "#8aa0b8", fontWeight: 700 }}>→</div>
                  )}
                </div>
              ))}
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
            <p style={{ color: "var(--subtle)", margin: "0 0 16px", lineHeight: 1.7 }}>
              已关联 {transitionRoles.length || 0} 个相关岗位；每个岗位至少给出 2 条换岗路径，便于比较转岗成本和技能桥接点。
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
              {(transitionRoles.length ? transitionRoles : []).map((role) => (
                <article key={role.title} style={{ border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, background: "#fff", padding: 16 }}>
                  <h3 style={{ margin: "0 0 8px", fontSize: "1rem" }}>{role.title}</h3>
                  <p style={{ margin: "0 0 12px", color: "var(--subtle)", fontSize: "0.8125rem", lineHeight: 1.6 }}>{role.description}</p>
                  <div style={{ display: "grid", gap: 10 }}>
                    {(role.paths ?? []).slice(0, 3).map((path) => (
                      <div key={path.steps.join("-")} style={{ padding: 12, borderRadius: 8, background: "#f8fafc" }}>
                        <strong style={{ display: "block", marginBottom: 6, fontSize: "0.875rem" }}>{path.steps.join(" → ")}</strong>
                        <p style={{ margin: "0 0 8px", color: "var(--subtle)", fontSize: "0.8125rem", lineHeight: 1.6 }}>{path.description}</p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {(path.skill_bridge ?? []).map((skill) => (
                            <span key={skill} style={{ padding: "4px 8px", borderRadius: 8, background: "#fff4e5", color: "#8a4b00", fontSize: "0.75rem", fontWeight: 600 }}>{skill}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
            {transitionRoles.length === 0 && (
              <ul className="plain-list">
                {alternatePaths.map((path: string[]) => (
                  <li key={path.join("-")}>{path.join(" → ")}</li>
                ))}
              </ul>
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
