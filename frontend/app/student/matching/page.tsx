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
  const [totalScore, setTotalScore] = useState<number | null>(null);
  const [dimensions, setDimensions] = useState<Array<{ dimension: string; score: number; weight: number; reasoning: string }>>([]);
  const [gapItems, setGapItems] = useState<Array<{ name: string; suggestion: string }>>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [summary, setSummary] = useState("暂无数据");
  const [loading, setLoading] = useState(true);
  const [isHistoricalView, setIsHistoricalView] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        let matching = null;
        // Extract match ID from history parameter (format: "match-{id}")
        if (historyId && historyId.startsWith("match-")) {
          const matchId = parseInt(historyId.replace("match-", ""), 10);
          if (!isNaN(matchId)) {
            setIsHistoricalView(true);
            matching = await getMatchResult(matchId);
          }
        } else {
          // Load latest data
          const sess = await getStudentSession();
          if (!sess.student_id || !sess.suggested_job_code) { setLoading(false); return; }
          matching = await getMatching(sess.student_id, sess.suggested_job_code);
        }

        if (matching) {
          setTotalScore(typeof matching.total_score === "number" ? matching.total_score : null);
          setDimensions(Array.isArray(matching?.dimensions) ? matching.dimensions : []);
          setGapItems(Array.isArray(matching?.gap_items) ? matching.gap_items : []);
          setSuggestions(Array.isArray(matching?.suggestions) ? matching.suggestions : []);
          setSummary(matching?.summary ?? "暂无数据");
        }
      } catch {} finally { setLoading(false); }
    })();
  }, [historyId]);

  const hasAnalysis = dimensions.length > 0 || totalScore != null;

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
            {totalScore != null && (
              <div style={{ textAlign: "center", marginBottom: 20 }}>
                <div style={{ fontSize: "2.5rem", fontWeight: 700, color: "#1976d2" }}>{totalScore}</div>
                <div style={{ fontSize: "0.875rem", color: "#666" }}>综合匹配得分</div>
              </div>
            )}
            <div className="comparison-grid">
              <SectionCard title="四维评分">
                {dimensions.length === 0 ? (
                  <p className="empty-message">历史记录暂无四维评分数据</p>
                ) : (
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
                )}
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
            {suggestions.length > 0 && (
              <SectionCard title="行动建议">
                <ul className="timeline">
                  {suggestions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </SectionCard>
            )}
            <SectionCard title="综合结论">
              <p>{summary}</p>
            </SectionCard>
          </>
        )}
    </div>
  );
}
