// Admin API - 调用 Filmate Server

const API_BASE = "/api/v1";

export interface User {
  id: number;
  username: string;
  email: string | null;
  role: "admin" | "user";
  is_active: boolean;
  credits: number;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// 存储 token
let token: string | null = localStorage.getItem("admin_token");

export function setToken(t: string) {
  token = t;
  localStorage.setItem("admin_token", t);
}

export function getToken() {
  return token;
}

export function clearToken() {
  token = null;
  localStorage.removeItem("admin_token");
}

function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...options?.headers },
  }).then((res) => {
    if (res.status === 401) {
      clearToken();
      window.location.href = "/login";
      throw new Error("未登录");
    }
    if (res.status === 403) {
      throw new Error("无权限");
    }
    if (!res.ok) {
      return res.json().then((d) => Promise.reject(d.detail || "请求失败"));
    }
    return res.json();
  });
}

// ============ 登录 ============
export const authApi = {
  login: (username: string, password: string) =>
    request<LoginResponse>("/users/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
};

// ============ 用户管理 ============
export const usersApi = {
  list: () => request<User[]>("/users"),
  get: (id: number) => request<User>(`/users/${id}`),
  create: (data: Partial<User> & { password: string }) =>
    request<User>("/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: Partial<User>) =>
    request<User>(`/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (id: number) =>
    request<void>(`/users/${id}`, { method: "DELETE" }),
};

// ============ 配置 ============
export const configApi = {
  get: () => request("/config"),
  update: (data: Record<string, unknown>) =>
    request("/config", { method: "PUT", body: JSON.stringify(data) }),
};

// ============ 统计数据 ============
export const statsApi = {
  get: () => request("/stats"),
};

export default { authApi, usersApi, configApi, statsApi };
