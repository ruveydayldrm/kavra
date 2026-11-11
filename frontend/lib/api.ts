export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export type QType = "mcq" | "tf" | "cloze" | "open";
export type Difficulty = "easy" | "medium" | "hard";

export type Locator = {
  kind: "page" | "slide" | "para" | "image" | "time";
  page?: number;
  page_end?: number;
  line_start?: number;
  line_end?: number;
  slide?: number;
  slide_end?: number;
  para?: number;
  para_end?: number;
  start?: number;
  end?: number;
  quote_score?: number;
};

export type Source = {
  quote: string;
  loc: Locator;
  document: { id: number; title: string; kind: string };
  url: string | null;
  context: string | null;
};

export type PublicQuestion = {
  id: number;
  document_id: number;
  topic_id: number | null;
  topic: string | null;
  type: QType;
  difficulty: Difficulty;
  stem: string;
  options: string[];
  key_point_count: number;
  is_new?: boolean;
};

export type FullQuestion = PublicQuestion & {
  correct_index: number;
  answer: string;
  accepted: string[];
  key_points: string[];
  explanation: string;
  source: Source;
  status: string;
  audit: Record<string, unknown>;
  generator: string;
  auditor: string;
};

export type CheckResult = {
  correct: boolean;
  score: number;
  correct_index?: number;
  answer?: string;
  near_miss?: boolean;
  covered?: number[];
  missing?: number[];
  key_points?: string[];
  suggested_rating: 1 | 2 | 3 | 4;
  question: FullQuestion;
};

export type Job = { id: number; status: "queued" | "running" | "done" | "failed"; progress: number; stage: string; message: string };

export type DocSummary = {
  generated: number;
  kept: number;
  repaired: number;
  rejected: Record<string, number>;
  remaining_chunks: number;
  errors: string[];
};

export type Doc = {
  id: number;
  title: string;
  kind: "pdf" | "pptx" | "docx" | "image" | "youtube" | "text";
  lang: string;
  status: "queued" | "processing" | "ready" | "partial" | "failed";
  error: string | null;
  created_at: number;
  questions: number;
  topics: number;
  summary: DocSummary | null;
  job: Job | null;
  video_id?: string | null;
};

export type TopicMastery = {
  id: number;
  document_id: number;
  document_title: string;
  title: string;
  summary: string;
  total: number;
  seen: number;
  mastery: number;
  accuracy: number | null;
  attempts: number;
  weakness?: number;
};

export type Quality = {
  kept: number;
  flagged: number;
  repaired: number;
  rejected: Record<string, number>;
  candidates: number;
  acceptance_rate: number | null;
  flag_rate: number | null;
  llm_calls: number;
  cache_hits: number;
  tokens: number;
  providers: { provider: string; model: string; role: string; n: number; ok: number }[];
  cost_usd: number;
};

export type DocDetail = Doc & { topic_list: TopicMastery[]; quality: Quality };

export type HeatDay = { date: string; count: number; correct: number };

export type Overview = {
  due: number;
  new: number;
  reviewed_today: number;
  correct_today: number;
  next_due_at: number | null;
  streak: { current: number; best: number; studied_today: boolean };
  heatmap: HeatDay[];
  weak_topics: TopicMastery[];
  mastery: TopicMastery[];
  totals: { documents: number; questions: number; reviews: number };
};

export type Queue = {
  items: PublicQuestion[];
  due_count: number;
  new_count: number;
  next_due_at: number | null;
  new_remaining: number;
};

export type Exam = {
  id: number;
  title: string;
  question_ids: number[];
  minutes: number;
  started_at: number;
  questions: PublicQuestion[];
};

export type ExamItem = CheckResult & { question_id: number; response: unknown; skipped?: boolean };

export type ExamReport = {
  exam_id: number;
  score: number;
  total: number;
  ratio: number;
  elapsed_s: number;
  minutes: number;
  topics: { topic: string; total: number; score: number; ratio: number }[];
  items: ExamItem[];
};

export type Health = {
  ok: boolean;
  local_mode: boolean;
  chains: Record<string, string[]>;
  keys: { gemini: boolean; groq: boolean };
  embedder: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "offline");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  overview: () => request<Overview>("/api/stats/overview"),
  quality: () => request<Quality>("/api/stats/quality"),
  documents: () => request<Doc[]>("/api/documents"),
  document: (id: number) => request<DocDetail>(`/api/documents/${id}`),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  resume: (id: number) => post<{ job_id: number }>(`/api/documents/${id}/resume`),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ id: number; job_id: number }>("/api/documents", { method: "POST", body: fd });
  },
  youtube: (url: string) => post<{ id: number; job_id: number }>("/api/documents/youtube", { url }),
  questions: (documentId: number) => request<FullQuestion[]>(`/api/questions?document_id=${documentId}`),
  queue: (p: { document_id?: number; topic_id?: number } = {}) => {
    const qs = new URLSearchParams();
    if (p.document_id) qs.set("document_id", String(p.document_id));
    if (p.topic_id) qs.set("topic_id", String(p.topic_id));
    return request<Queue>(`/api/study/queue?${qs}`);
  },
  check: (question_id: number, response: unknown, duration_ms: number) =>
    post<CheckResult>("/api/study/check", { question_id, response, duration_ms }),
  review: (b: { question_id: number; rating: number; correct: boolean; response: unknown; duration_ms: number; score: number }) =>
    post<{ due: number }>("/api/study/review", b),
  flag: (id: number, reason: string, note: string) => post<{ ok: boolean }>(`/api/questions/${id}/flag`, { reason, note }),
  newExam: (b: { count: number; minutes: number; document_ids?: number[] }) => post<Exam>("/api/exams", b),
  submitExam: (id: number, answers: Record<string, unknown>) => post<ExamReport>(`/api/exams/${id}/submit`, { answers }),
  exams: () => request<{ id: number; title: string; minutes: number; started_at: number; finished_at: number | null; ratio: number | null; total: number | null }[]>("/api/exams"),
};

export function jobEvents(jobId: number, onJob: (j: Job) => void): () => void {
  const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    const j = JSON.parse(e.data) as Job;
    onJob(j);
    if (j.status === "done" || j.status === "failed") es.close();
  };
  es.onerror = () => es.close();
  return () => es.close();
}

export function fileUrl(url: string | null): string | null {
  if (!url) return null;
  return url.startsWith("/api/") ? `${API_BASE}${url}` : url;
}
