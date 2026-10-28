// 统一 API 客户端：自动附带 JWT，401 时跳登录
// 地址优先级：环境变量 VITE_API_BASE（Vercel 部署时设为后端隧道地址）> 本地/局域网/隧道自适应
const BASE =
  import.meta.env.VITE_API_BASE ??
  (location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : location.hostname.endsWith(".trycloudflare.com") ||
        location.hostname.endsWith(".cpolar.top") ||
        location.hostname.endsWith(".vercel.app")
      ? "" // 同源：隧道由 vite preview 代理 /api；Vercel 由 vercel.json 的 proxy 配置转发
      : `http://${location.hostname}:8000`);

/** cpolar 免费版两条隧道（前端+API）主机号不同：从本地存储取 API 隧道地址，否则回退 BASE */
function apiBase(): string {
  const saved = localStorage.getItem("cpolar_api_base");
  return saved || BASE;
}

/** 设置 API 隧道地址（Login 页加载时由后端配置接口提供） */
export function setApiBase(base: string) {
  localStorage.setItem("cpolar_api_base", base);
}

/** 探测可用的 API 地址：候选 = [缓存地址, BASE, 页面同源]，
 *  逐个尝试 /api/health，第一个通的写入缓存。解决隧道地址变更后旧缓存失灵。 */
export async function probeApiBase(): Promise<string> {
  const candidates = [apiBase(), BASE, ""].filter(
    (v, i, arr) => v !== undefined && arr.indexOf(v) === i,
  );
  for (const c of candidates) {
    try {
      const r = await fetch(`${c}/api/health`, { cache: "no-store" });
      if (r.ok) {
        const saved = localStorage.getItem("cpolar_api_base");
        if (saved !== c) localStorage.setItem("cpolar_api_base", c);
        return c;
      }
    } catch {
      /* 该候选不可达，试下一个 */
    }
  }
  return apiBase(); // 全部失败时维持现状，让上层报错
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("token");
  const resp = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (resp.status === 401) {
    localStorage.removeItem("token");
    if (location.pathname !== "/login") location.href = "/login";
    throw new ApiError(401, "请先登录");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(resp.status, body.detail ?? "请求失败");
  }
  return resp.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: async <T>(path: string, file: File) => {
    const token = localStorage.getItem("token");
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new ApiError(resp.status, body.detail ?? "上传失败");
    }
    return resp.json() as Promise<T>;
  },
  base: BASE,
};

/** <video>/<img> 标签用的媒体地址：追加 token 查询参数（标签请求无法带 Authorization 头） */
export function mediaUrl(path: string): string {
  const token = localStorage.getItem("token");
  const sep = path.includes("?") ? "&" : "?";
  return `${apiBase()}${path}${sep}token=${encodeURIComponent(token ?? "")}`;
}

// ===== 类型定义（与后端 schema 一致）=====
export interface ProviderInfo {
  name: string;
  label: string;
  supports_i2v: boolean;
  supports_first_frame: boolean;
}

export interface TaskOut {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  task_type: "t2v" | "i2v";
  provider: string;
  prompt: string;
  optimized_prompt: string | null;
  duration: number;
  aspect_ratio: string;
  has_video: boolean;
  created_at: string | null;
  error: string | null;
  seed?: number | null;
  finished_at?: string | null;
}

export interface OptimizeResult {
  optimized_prompt: string;
  negative_prompt: string;
  shot_suggestions: string[];
}

export interface StoryboardOut {
  id: string;
  title: string;
  status: "draft" | "generating" | "done" | "partial";
  shot_count: number;
  has_final_video: boolean;
  error: string | null;
  created_at: string | null;
  owner?: string;
  shots?: ShotOut[];
}

export interface ShotOut {
  task_id: string;
  shot_index: number;
  prompt: string;
  optimized_prompt: string | null;
  status: TaskOut["status"];
  progress: number;
  duration: number;
  has_video: boolean;
  error: string | null;
}

export interface UserInfo {
  username: string;
  is_admin: boolean;
  daily_quota: number;
  quota_used_today: number;
  quota_enabled?: boolean;
}

// ===== 文生图（与视频任务相互独立）=====
export interface ImageProviderInfo {
  name: string;
  label: string;
  supports_e2i: boolean;
}

export interface ImageTaskOut {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  task_type: "t2i" | "e2i";
  provider: string;
  prompt: string;
  optimized_prompt: string | null;
  size: string;
  seed: number | null;
  guidance: number;
  has_image: boolean;
  created_at: string | null;
  error: string | null;
}

export interface ImageQuota {
  used: number;
  quota: number;
  unlimited?: boolean;
}

export interface ImageOptimizeResult {
  optimized_prompt: string;
  negative_prompt: string;
}

export interface AdminStats {
  user_count: number;
  task_count: number;
  by_status: Record<string, number>;
  daily: { date: string; count: number }[];
}
