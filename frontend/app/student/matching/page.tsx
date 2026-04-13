"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SectionCard } from "@/components/SectionCard";
import { EmptyState } from "@/components/EmptyState";
import { getStudentSession, getMatching, getMatchResult } from "@/lib/api";
import { Icon } from "@/components/Icon";

export default function StudentMatchingPage() {
  const searchParams = useSearchParams();
  const historyId = searchParams.get("history");
  const [dimensions, setDimensions] = useState<Array<{ dimension: string; score: number; weight: number; reasoning: string }>>([]);
  const [gapItems, setGapItems] = useState<Array<{ name: string; suggestion: string }>>([]);
  const [summary, setSummary] = useState("暂无数据");
  const [loading, setLoading] = useState(true);
  const [isHistoricalView, setIsHistoricalView] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        // Extract match ID from history parameter (format: "match-{id}")
        if (historyId && historyId.startsWith("match-")) {
          const matchId = parseInt(historyId.replace("match-", ""), 10);
          if (!isNaN(matchId)) {
            setIsHistoricalView(true);
            const matching = await getMatchResult(matchId);
            setDimensions(Array.isArray(matching?.dimensions) ? matching.dimensions : []);
            setGapItems(Array.isArray(matching?.gap_items) ? matching.gap_items : []);
            setSummary(matching?.summary ?? "暂无数据");
            setLoading(false);
            return;
          }
        }

        // Load latest data
        const sess = await getStudentSession();
        const jobCode = sess.resolved_job_code || sess.target_job_code || sess.suggested_job_code || "";
        if (!sess.student_id || !jobCode) { setLoading(false); return; }
        const matching = await getMatching(sess.student_id, jobCode);
        setDimensions(Array.isArray(matching?.dimensions) ? matching.dimensions : []);
        setGapItems(Array.isArray(matching?.gap_items) ? matching.gap_items : []);
        setSummary(matching?.summary ?? "暂无数据");
      } catch {} finally { setLoading(false); }
    })();
  }, [historyId]);

  const hasAnalysis = dimensions.length > 0;

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>匹配分析</h1>
            {isHistoricalView && (
              <p style={{ fontSize: "0.875rem", color: "#f57c00", margin: "4px 0 0" }}>
                ⚠️ 正在查看历史数据
              </p>
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
        ) : !hasAnalysis ? (
          <EmptyState
            icon={<Icon name="target" size={32} />}
            title="还没有匹配分析结果"
            description="上传简历并指定目标岗位后，系统将进行四维评分分析，识别你的优势和需要提升的能力。"
            actionLabel="开始智能匹配"
            actionHref="/student/upload"
          />
        ) : (
          <>
            <div className="comparison-grid">
              <SectionCard title="四维评分">
                <table className="comparison-table" aria-label="四维评分对比表">
                  <thead>
                    <tr>
                      <th>评分方面</th>
                      <th>得分</th>
                      <th>权重</th>
                      <th>评价</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dimensions.map((item) => (
                      <tr key={item.dimension}>
                        <td><strong>{item.dimension}</strong></td>
                        <td>{item.score} 分</td>
                        <td>{item.weight}</td>
                        <td>{item.reasoning}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </SectionCard>
              <SectionCard title="差距项与提升建议">
                {gapItems.length === 0 ? (
                  <p className="empty-message">完美匹配！</p>
                ) : (
                  <ul className="plain-list">
                    {gapItems.map((gap) => (
                      <li key={gap.name}>
                        <strong>{gap.name}</strong>：{gap.suggestion}
                      </li>
                    ))}
                  </ul>
                )}
              </SectionCard>
            </div>
            <SectionCard title="综合结论">
              <p>{summary}</p>
            </SectionCard>
          </>
        )}
    </div>
  );
}
