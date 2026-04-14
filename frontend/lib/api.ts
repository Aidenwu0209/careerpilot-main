import { demoJobTemplates, demoMatching, demoPath, demoReportMarkdown, demoStudentProfile, type JobDetail } from "./demo-data";
export type { JobDetail };

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type StudentProfile = typeof demoStudentProfile;
export type MatchingResult = typeof demoMatching;
export type PathPlan = typeof demoPath;
export type SchedulerJobItem = {
  job_name: string;
  cron_expr: string;
  status: string;
  job_type: string;
};
export type ReportDraft = {
  report_id: number;
  student_id: number;
  job_code: string;
  markdown_content: string;
  content: Record<string, unknown>;
  status: string;
  path_recommendation_id: number | null;
  profile_version_id: number | null;
  match_result_id: number | null;
  analysis_run_id: number | null;
};

export type StudentSession = {
  student_id: number | null;
  user_id: number;
  major: string;
  grade: string;
  career_goal: string;
  target_job_code: string;
  target_job_title: string;
  suggested_job_code: string | null;
  suggested_job_title: string | null;
  resolved_job_code: string;
  resolved_job_title: string;
};

export class APIError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public isNetworkError: boolean = false,
    public errorCode?: string,
    public retryable?: boolean,
  ) {
    super(message);
    this.name = "APIError";
  }
}

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
    const headers: Record<string, string> = {
      ...getAuthHeaders(),
      ...(init?.headers as Record<string, string> || {}),
    };
    if (!isFormData) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      headers,
    });

    if (!response.ok) {
      let detail = `请求失败 (${response.status})`;
      let errorCode: string | undefined;
      let retryable: boolean | undefined;
      try {
        const body = await response.json();
        if (body.detail) {
          if (typeof body.detail === "object" && body.detail !== null) {
            detail = body.detail.message || JSON.stringify(body.detail);
            errorCode = body.detail.error_code;
            retryable = body.detail.retryable;
          } else {
            detail = body.detail;
          }
        } else if (body.message) {
          detail = body.message;
        }
        if (body.error_code && !errorCode) errorCode = body.error_code;
        if (body.retryable !== undefined && retryable === undefined) retryable = body.retryable;
      } catch {}
      console.error(`[API Error] ${path}:`, detail);
      throw new APIError(response.status, detail, false, errorCode, retryable);
    }

    const data = await response.json();
    return data as T;
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }

    const networkError = new APIError(
      0,
      `Network error: ${error instanceof Error ? error.message : "Unknown error"}`,
      true
    );
    console.error(`[Network Error] ${path}:`, networkError.message);
    throw networkError;
  }
}

export async function getStudentSession(): Promise<StudentSession> {
  return request<StudentSession>("/students/me");
}

export async function updateTargetJob(jobCode: string, jobTitle: string): Promise<{ ok: boolean; target_job_code: string; target_job_title: string; analysis_run_id: number | null }> {
  return request("/students/me/target-job", {
    method: "PUT",
    body: JSON.stringify({ job_code: jobCode, job_title: jobTitle }),
  });
}

export async function getStudentProfile(studentId: number): Promise<StudentProfile> {
  try {
    return await request<StudentProfile>(`/student-profiles/${studentId}`);
  } catch (error) {
    if (error instanceof APIError && error.isNetworkError && process.env.NODE_ENV === "development") {
      console.warn("[Fallback] Using demo data for student profile due to network error");
      return demoStudentProfile;
    }
    throw error;
  }
}

export async function getMatching(studentId: number, jobCode: string): Promise<MatchingResult> {
  try {
    return await request<MatchingResult>("/matching/analyze", {
      method: "POST",
      body: JSON.stringify({ student_id: studentId, job_code: jobCode })
    });
  } catch (error) {
    if (error instanceof APIError && error.isNetworkError && process.env.NODE_ENV === "development") {
      console.warn("[Fallback] Using demo data for matching due to network error");
      return demoMatching;
    }
    throw error;
  }
}

export async function getMatchResult(matchId: number): Promise<MatchingResult> {
  return await request<MatchingResult>(`/matching/${matchId}`);
}

export async function getPathPlan(studentId: number, jobCode: string): Promise<PathPlan> {
  try {
    const response = await request<{ data: PathPlan }>("/career-paths/plan", {
      method: "POST",
      body: JSON.stringify({ student_id: studentId, job_code: jobCode })
    });
    return response.data;
  } catch (error) {
    if (error instanceof APIError && error.isNetworkError && process.env.NODE_ENV === "development") {
      console.warn("[Fallback] Using demo data for path plan due to network error");
      return demoPath;
    }
    throw error;
  }
}

export async function getPathResult(pathId: number): Promise<PathPlan> {
  const response = await request<{ data: PathPlan }>(`/career-paths/${pathId}`);
  return response.data;
}

export async function getJobTemplates(): Promise<JobDetail[]> {
  try {
    const response = await request<{ data: JobDetail[] }>("/jobs/profiles/templates");
    return response.data;
  } catch (error) {
    console.warn("[Fallback] Using demo data for job templates:", error instanceof Error ? error.message : error);
    if (process.env.NODE_ENV === "development") {
      return demoJobTemplates;
    }
    throw error;
  }
}

export type JobExploreItem = Omit<JobDetail, "category"> & {
  job_code?: string;
  category: string;
  industry?: string;
  location?: string;
  company_name?: string;
  company_size?: string;
  ownership_type?: string;
  company_intro?: string;
  source?: string;
};

export async function getJobExplorationJobs(limit: number = 180): Promise<JobExploreItem[]> {
  try {
    const response = await request<{ data: JobExploreItem[] }>(`/jobs/explore?limit=${limit}`);
    return response.data;
  } catch (error) {
    console.warn("[Fallback] Using job templates for exploration:", error instanceof Error ? error.message : error);
    if (process.env.NODE_ENV === "development") {
      return demoJobTemplates.map((job) => ({ ...job }));
    }
    throw error;
  }
}

export async function generateReport(studentId: number, jobCode: string): Promise<ReportDraft> {
  try {
    return await request<ReportDraft>("/reports/generate", {
      method: "POST",
      body: JSON.stringify({ student_id: studentId, job_code: jobCode })
    });
  } catch (error) {
    if (error instanceof APIError && error.isNetworkError && process.env.NODE_ENV === "development") {
      console.warn("[Fallback] Using demo data for report due to network error");
      return {
        report_id: 1,
        student_id: studentId,
        job_code: jobCode,
        markdown_content: demoReportMarkdown,
        content: {},
        status: "draft",
        path_recommendation_id: null,
        profile_version_id: null,
        match_result_id: null,
        analysis_run_id: null,
      };
    }
    throw error;
  }
}

export async function getReport(reportId: number): Promise<ReportDraft> {
  return request<ReportDraft>(`/reports/${reportId}`);
}

export type ReportCheckResult = {
  report_id: number;
  is_complete: boolean;
  missing_sections: string[];
  suggestions: string[];
};

export type ReportExportResult = {
  report_id: number;
  exported: {
    format: string;
    path: string;
    file_name: string;
  };
};

export async function polishReport(reportId: number, markdownContent: string): Promise<ReportDraft> {
  return request<ReportDraft>("/reports/polish", {
    method: "POST",
    body: JSON.stringify({ report_id: reportId, markdown_content: markdownContent }),
  });
}

export async function saveReport(reportId: number, markdownContent: string): Promise<{ report_id: number; status: string; markdown_content: string }> {
  return request("/reports/save", {
    method: "POST",
    body: JSON.stringify({ report_id: reportId, markdown_content: markdownContent }),
  });
}

export async function checkReport(reportId: number): Promise<ReportCheckResult> {
  return request<ReportCheckResult>("/reports/check", {
    method: "POST",
    body: JSON.stringify({ report_id: reportId }),
  });
}

export async function exportReport(reportId: number, format: "pdf" | "docx"): Promise<ReportExportResult> {
  return request<ReportExportResult>("/reports/export", {
    method: "POST",
    body: JSON.stringify({ report_id: reportId, format }),
  });
}

export async function parseOCR(uploadedFileId: number, documentType: string = "resume"): Promise<{ raw_text: string; layout_blocks: unknown[]; structured_json: Record<string, unknown> }> {
  return request("/ocr/parse", {
    method: "POST",
    body: JSON.stringify({ uploaded_file_id: uploadedFileId, document_type: documentType })
  });
}

export async function generateStudentProfile(studentId: number, uploadedFileIds: number[], mode: "current_resume" | "merged_materials" = "current_resume"): Promise<StudentProfile> {
  return request<StudentProfile>("/student-profiles/generate", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, uploaded_file_ids: uploadedFileIds, mode, manual_input: null })
  });
}

export type ProfileVersionItem = {
  id: number;
  version_no: number;
  uploaded_file_ids: number[];
  file_summaries: { file_id: number; file_name: string; file_type: string; summary: string }[];
  source_files: string;
  snapshot: StudentProfile;
  evidence_snapshot: { source: string; excerpt: string; confidence: number }[];
  created_at: string;
};

export async function getProfileVersions(studentId: number): Promise<ProfileVersionItem[]> {
  const res = await request<{ items: ProfileVersionItem[] }>(`/student-profiles/${studentId}/versions`);
  return res.items;
}

export async function getProfileVersionDetail(studentId: number, versionId: number): Promise<ProfileVersionItem> {
  return request<ProfileVersionItem>(`/student-profiles/${studentId}/versions/${versionId}`);
}

function generateDemoChatReply(message: string): string {
  const keywords = ["技能", "职业", "岗位", "方向", "入行", "前景"];
  if (keywords.some((kw) => message.includes(kw))) {
    return `根据你的描述，我为你分析如下：

1. **职业方向建议**：建议关注互联网产品、数据分析等数字化岗位方向，这些领域对复合型人才需求旺盛。
2. **核心技能**：重点提升数据分析、项目管理和跨部门沟通能力。
3. **行动建议**：
   - 短期：梳理已有项目经验，提炼可量化的成果
   - 中期：寻找实习机会，积累行业认知
   - 长期：考取相关职业证书，提升竞争力

你可以上传简历让我做更精准的分析，也可以继续提问其他职业方向的问题。`;
  }
  return `你好！我是职航智策 AI 助手，专门帮助大学生进行职业规划。

你可以问我：
- 某个岗位需要什么技能？
- 如何从当前专业转入某个职业方向？
- 某个行业的发展前景如何？

请描述你的问题，我会尽力为你解答！`;
}

export async function sendChatMessage(message: string): Promise<{ reply: string }> {
  try {
    return await request<{ reply: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message })
    });
  } catch (error) {
    if (process.env.NODE_ENV === "development" && error instanceof APIError && error.isNetworkError) {
      console.warn("[Fallback] Using demo reply for chat due to error:", error instanceof Error ? error.message : error);
      return { reply: generateDemoChatReply(message) };
    }
    throw error;
  }
}

export async function getGreeting(): Promise<{ greeting: string; subline: string }> {
  try {
    return await request<{ greeting: string; subline: string }>("/chat/greeting");
  } catch {
    return { greeting: "你好，想了解什么职业方向？", subline: "输入你感兴趣的岗位方向或上传简历，AI 帮你分析" };
  }
}

export async function registerAccount(
  username: string,
  password: string,
  full_name: string,
  role: string,
): Promise<{ access_token: string; role: string; user_id: number; username: string; full_name: string }> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, full_name, role }),
  });
}

export async function getSchedulerJobs(): Promise<SchedulerJobItem[]> {
  try {
    return await request<SchedulerJobItem[]>("/scheduler/jobs");
  } catch (error) {
    if (error instanceof APIError && error.isNetworkError && process.env.NODE_ENV === "development") {
      console.warn("[Fallback] Using demo data for scheduler jobs due to network error");
      return [
        { job_name: "weekly_growth_review", cron_expr: "0 9 * * 1", status: "active", job_type: "review" },
        { job_name: "weekly_resource_push", cron_expr: "0 10 * * 3", status: "active", job_type: "resource_push" }
      ];
    }
    throw error;
  }
}

export type UploadedFileInfo = {
  id: number;
  file_name: string;
  file_type: string;
  content_type: string;
  created_at: string | null;
};

export async function listFiles(): Promise<UploadedFileInfo[]> {
  const res = await request<{ data: UploadedFileInfo[] }>("/files");
  return res.data ?? [];
}

export async function uploadFile(file: File, ownerId: number, fileType: string): Promise<{ id: number; file_name: string; file_type: string; created_at: string | null; url: string }> {
  const form = new FormData();
  form.append("upload", file);
  form.append("owner_id", String(ownerId));
  form.append("file_type", fileType);
  const res = await request<{ data: { id: number; file_name: string; file_type: string; created_at: string | null; url: string } }>("/files/upload", {
    method: "POST",
    body: form,
  });
  return res.data;
}

export async function deleteFile(fileId: number): Promise<void> {
  await request(`/files/${fileId}`, { method: "DELETE" });
}

export async function clearFiles(): Promise<void> {
  await request("/files/clear", { method: "DELETE" });
}

export type AdminUser = {
  id: number;
  username: string;
  full_name: string;
  role: string;
  email: string;
  created_at: string | null;
  updated_at: string | null;
};

export async function getAdminUsers(): Promise<{ total: number; items: AdminUser[] }> {
  const res = await request<{ data: { total: number; items: AdminUser[] } }>("/admin/users");
  return res.data;
}

export type AdminStatsOverview = {
  total_users: number;
  total_jobs: number;
  total_reports: number;
  avg_match_score: number;
};

export async function getAdminStatsOverview(): Promise<AdminStatsOverview> {
  const res = await request<{ data: AdminStatsOverview }>("/admin/stats/overview");
  return res.data;
}

export type TrendDataPoint = {
  date: string;
  reports: number;
  users: number;
};

export async function getAdminStatsTrends(days: number = 14): Promise<TrendDataPoint[]> {
  const res = await request<{ data: TrendDataPoint[] }>(`/admin/stats/trends?days=${days}`);
  return res.data;
}

export type WeeklyDataPoint = {
  week: string;
  reports: number;
  matches: number;
};

export async function getAdminStatsWeekly(weeks: number = 8): Promise<WeeklyDataPoint[]> {
  const res = await request<{ data: WeeklyDataPoint[] }>(`/admin/stats/weekly?weeks=${weeks}`);
  return res.data;
}

export type SystemHealth = {
  status: string;
  database: string;
  api_response_ms: number;
  last_check: string;
  version: string;
};

export async function getSystemHealth(): Promise<SystemHealth> {
  const res = await request<{ data: SystemHealth }>("/admin/system/health");
  return res.data;
}

export type TeacherStudentReport = {
  student_id: number;
  name: string;
  target_job: string;
  match_score: number;
  report_status: string;
  major: string;
  grade: string;
  career_goal: string;
};

export async function getTeacherStudentReports(): Promise<TeacherStudentReport[]> {
  const res = await request<{ data: TeacherStudentReport[] }>("/teacher/students/reports");
  return res.data;
}

export type DistributionItem = {
  name: string;
  count: number;
};

export async function getMatchDistribution(): Promise<DistributionItem[]> {
  const res = await request<{ data: DistributionItem[] }>("/teacher/stats/match-distribution");
  return res.data;
}

export type MajorDistributionItem = {
  name: string;
  value: number;
};

export async function getMajorDistribution(): Promise<MajorDistributionItem[]> {
  const res = await request<{ data: MajorDistributionItem[] }>("/teacher/stats/major-distribution");
  return res.data;
}

export type TeacherAdviceItem = {
  student_id: number;
  name: string;
  target_job: string;
  match_score: number;
  advice: string;
};

export async function getTeacherAdvice(): Promise<TeacherAdviceItem[]> {
  const res = await request<{ data: TeacherAdviceItem[] }>("/teacher/advice");
  return res.data;
}

export type RecommendedJob = {
  job_code: string;
  title: string;
  company: string;
  salary: string;
  location?: string;
  industry?: string;
  company_size?: string;
  ownership_type?: string;
  summary?: string;
  tags: string[];
  matched_tags?: string[];
  missing_tags?: string[];
  experience_tags?: string[];
  reason?: string;
  match_score: number | null;
  base_score?: number | null;
  experience_score?: number | null;
  skill_score?: number | null;
  potential_score?: number | null;
};

export async function getRecommendedJobs(): Promise<RecommendedJob[]> {
  const res = await request<{ items: RecommendedJob[] }>("/students/me/recommended-jobs");
  return res.items;
}

export type HistoryItem = {
  id: string;
  type: string;
  ref_id: number;
  title: string;
  desc: string;
  time: string;
};

export async function getStudentHistory(): Promise<HistoryItem[]> {
  const res = await request<{ items: HistoryItem[] }>("/students/me/history");
  return res.items;
}

export async function renameHistoryItem(recordType: string, refId: number, customTitle: string): Promise<void> {
  await request("/students/me/history/rename", {
    method: "PATCH",
    body: JSON.stringify({ record_type: recordType, ref_id: refId, custom_title: customTitle }),
  });
}

export type JobListItem = {
  job_code: string;
  title: string;
  skills: string[];
  weights: Record<string, number>;
};

export async function getJobsList(skip: number = 0, limit: number = 100): Promise<{ total: number; items: JobListItem[] }> {
  const res = await request<{ data: { total: number; items: JobListItem[]; pagination: { total: number } } }>(`/jobs?skip=${skip}&limit=${limit}`);
  return { total: res.data.pagination?.total ?? res.data.total ?? 0, items: res.data.items };
}

// --- Analysis Pipeline State ---

export type AnalysisRunState = {
  run_id: number;
  status: "pending" | "running" | "completed" | "failed";
  current_step: string;
  failed_step: string;
  error_detail: string;
  step_results: Record<string, boolean>;
};

export async function startAnalysisRun(studentId: number, jobCode: string, fileIds: number[]): Promise<AnalysisRunState> {
  return request<AnalysisRunState>("/analysis/start", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, job_code: jobCode, file_ids: fileIds }),
  });
}

export async function getAnalysisRun(runId: number): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}`);
}

export async function getLatestAnalysis(): Promise<AnalysisRunState> {
  return request<AnalysisRunState>("/analysis/latest");
}

export async function markStepRunning(runId: number, stepKey: string): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}/step/${stepKey}/running`, { method: "POST" });
}

export async function markStepComplete(runId: number, stepKey: string): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}/step/${stepKey}/complete`, { method: "POST" });
}

export async function markStepFailed(runId: number, stepKey: string, errorDetail: string): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}/step/${stepKey}/fail`, {
    method: "POST",
    body: JSON.stringify({ error_detail: errorDetail }),
  });
}

export async function markAnalysisComplete(runId: number): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}/complete`, { method: "POST" });
}

export async function resetAnalysisRun(runId: number): Promise<AnalysisRunState> {
  return request<AnalysisRunState>(`/analysis/${runId}/reset`, { method: "POST" });
}
