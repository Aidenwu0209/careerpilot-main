import { demoJobTemplates, demoMatching, demoPath, demoReportMarkdown, demoStudentProfile, type JobDetail } from "./demo-data";
export type { JobDetail };

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type StudentProfile = typeof demoStudentProfile;
export type MatchingResult = typeof demoMatching;
export type PathPlan = typeof demoPath;

export type VerticalGraphNode = {
  title: string;
  description: string;
  skills: string[];
  level: number;
  stage: string;
};

export type VerticalGraphEdge = {
  from: string;
  to: string;
  relation: string;
  description: string;
};

export type VerticalGraph = {
  title: string;
  description: string;
  nodes: VerticalGraphNode[];
  edges: VerticalGraphEdge[];
  promotion_paths: string[][];
  vertical_paths: Record<string, unknown>[];
};

export type TransitionPathItem = {
  steps: string[];
  relation: string;
  description: string;
  skill_bridge: string[];
};

export type TransitionRole = {
  title: string;
  description: string;
  skills: string[];
  paths: TransitionPathItem[];
};

export type TransitionGraph = {
  target: string;
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  role_paths: TransitionRole[];
  clusters: Record<string, unknown>[];
};
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
};

export type StudentSession = {
  student_id: number | null;
  user_id: number;
  major: string;
  grade: string;
  career_goal: string;
  confirmed_job_code: string | null;
  confirmed_job_title: string | null;
  suggested_job_code: string | null;
  suggested_job_title: string | null;
};

export class APIError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public isNetworkError: boolean = false
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
      try {
        const body = await response.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        else if (body.message) detail = body.message;
      } catch {}
      console.error(`[API Error] ${path}:`, detail);
      throw new APIError(response.status, detail, false);
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

export type TargetJob = {
  jobCode: string;
  jobTitle: string;
};

/**
 * Unified target job resolution.
 * Priority: user manually confirmed > session suggested (backend unified) > first recommended job.
 * Returns null when no target job can be determined.
 */
export async function resolveTargetJob(): Promise<TargetJob | null> {
  const session = await getStudentSession();
  if (session.suggested_job_code && session.suggested_job_title) {
    return { jobCode: session.suggested_job_code, jobTitle: session.suggested_job_title };
  }
  // Fallback: first recommended job with a valid job_code
  try {
    const jobs = await getRecommendedJobs();
    const first = jobs.find((j) => j.job_code);
    if (first) {
      return { jobCode: first.job_code, jobTitle: first.title };
    }
  } catch {
    // If recommended jobs fail, return null
  }
  return null;
}

export async function setTargetJob(jobCode: string, jobTitle: string): Promise<{ ok: boolean; confirmed_job_code: string; confirmed_job_title: string }> {
  return request("/students/me/target-job", {
    method: "PATCH",
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
        status: "draft"
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

export async function generateStudentProfile(studentId: number, uploadedFileIds: number[]): Promise<StudentProfile> {
  return request<StudentProfile>("/student-profiles/generate", {
    method: "POST",
    body: JSON.stringify({ student_id: studentId, uploaded_file_ids: uploadedFileIds, manual_input: null })
  });
}

export type ProfileVersionItem = {
  id: number;
  version_no: number;
  source_files: string;
  snapshot: StudentProfile;
  created_at: string;
};

export async function getProfileVersions(studentId: number): Promise<ProfileVersionItem[]> {
  const res = await request<{ items: ProfileVersionItem[] }>(`/student-profiles/${studentId}/versions`);
  return res.items;
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
    if (process.env.NODE_ENV === "development") {
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

export async function uploadFile(file: File, ownerId: number, fileType: string): Promise<{ id: number; file_name: string; url: string }> {
  const form = new FormData();
  form.append("upload", file);
  form.append("owner_id", String(ownerId));
  form.append("file_type", fileType);
  const res = await request<{ data: { id: number; file_name: string; url: string } }>("/files/upload", {
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
  matched_certificates?: string[];
  missing_certificates?: string[];
  experience_tags?: string[];
  intent_tags?: string[];
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

export type ApiKeyStatus = {
  configured: boolean;
  auth_mode: "qianfan" | "aistudio";
  api_key_masked: string | null;
  secret_key_masked: string | null;
  model_name: string | null;
};

type SaveApiKeyPayload = {
  api_key: string;
  secret_key?: string;
  auth_mode: "qianfan" | "aistudio";
};

type ApiKeyTestResult = {
  success: boolean;
  message: string;
};

const API_KEY_STATUS_STORAGE_KEY = "careerpilot_api_key_status";

const DEFAULT_API_KEY_STATUS: ApiKeyStatus = {
  configured: false,
  auth_mode: "qianfan",
  api_key_masked: null,
  secret_key_masked: null,
  model_name: null,
};

function maskCredential(value: string): string {
  if (!value) return "";
  if (value.length <= 8) {
    return `${value.slice(0, 2)}***${value.slice(-1)}`;
  }
  return `${value.slice(0, 4)}***${value.slice(-4)}`;
}

function readStoredApiKeyStatus(): ApiKeyStatus {
  if (typeof window === "undefined") {
    return DEFAULT_API_KEY_STATUS;
  }

  try {
    const raw = localStorage.getItem(API_KEY_STATUS_STORAGE_KEY);
    if (!raw) return DEFAULT_API_KEY_STATUS;
    const parsed = JSON.parse(raw) as Partial<ApiKeyStatus>;
    return {
      configured: Boolean(parsed.configured),
      auth_mode: parsed.auth_mode === "aistudio" ? "aistudio" : "qianfan",
      api_key_masked: parsed.api_key_masked ?? null,
      secret_key_masked: parsed.secret_key_masked ?? null,
      model_name: parsed.model_name ?? null,
    };
  } catch {
    return DEFAULT_API_KEY_STATUS;
  }
}

function writeStoredApiKeyStatus(status: ApiKeyStatus): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(API_KEY_STATUS_STORAGE_KEY, JSON.stringify(status));
}

export async function generateDemoReport(): Promise<ReportDraft> {
  return {
    report_id: 0,
    student_id: 1,
    job_code: "DEMO",
    markdown_content: demoReportMarkdown,
    content: {},
    status: "draft",
  };
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  return readStoredApiKeyStatus();
}

export async function saveApiKey(payload: SaveApiKeyPayload): Promise<ApiKeyStatus> {
  const status: ApiKeyStatus = {
    configured: true,
    auth_mode: payload.auth_mode,
    api_key_masked: maskCredential(payload.api_key),
    secret_key_masked: payload.secret_key ? maskCredential(payload.secret_key) : null,
    model_name: payload.auth_mode === "qianfan" ? "ERNIE via Qianfan" : "ERNIE via AI Studio",
  };
  writeStoredApiKeyStatus(status);
  return status;
}

export async function deleteApiKey(): Promise<ApiKeyStatus> {
  writeStoredApiKeyStatus(DEFAULT_API_KEY_STATUS);
  return DEFAULT_API_KEY_STATUS;
}

export async function testApiKey(): Promise<ApiKeyTestResult> {
  const status = readStoredApiKeyStatus();
  if (!status.configured) {
    return {
      success: false,
      message: "当前还没有保存 API Key。",
    };
  }

  return {
    success: true,
    message: "密钥格式已保存。本地演示环境当前仍默认使用内置 mock 模式。",
  };
}
