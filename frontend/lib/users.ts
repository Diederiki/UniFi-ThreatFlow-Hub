import { api } from "./api";

export type Role = "admin" | "operator" | "viewer";

export type AppUser = {
  id: number;
  email: string;
  name: string | null;
  role: Role;
  enabled: boolean;
  auth_method: string;
  sso_subject: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UserList = { items: AppUser[]; total: number };

export type UserCreateInput = {
  email: string;
  name?: string | null;
  role: Role;
  enabled?: boolean;
  password: string;
};

export type UserUpdateInput = {
  name?: string | null;
  role?: Role;
  enabled?: boolean;
};

export const usersApi = {
  list:    () => api<UserList>("/users"),
  create:  (body: UserCreateInput) => api<AppUser>("/users", { method: "POST", body: JSON.stringify(body) }),
  update:  (id: number, body: UserUpdateInput) => api<AppUser>(`/users/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete:  (id: number) => api<void>(`/users/${id}`, { method: "DELETE" }),
  resetPassword: (id: number, new_password: string) =>
    api<void>(`/users/${id}/password`, { method: "POST", body: JSON.stringify({ new_password }) }),
};

export type SsoConfig = {
  enabled: boolean;
  tenant_id: string;
  client_id: string;
  redirect_uri: string;
  auto_provision: boolean;
  default_role: Role;
  has_client_secret: boolean;
};

export type SsoConfigUpdate = {
  enabled: boolean;
  tenant_id: string;
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  auto_provision: boolean;
  default_role: Role;
};

export type SsoInfo = {
  enabled: boolean;
  button_label: string;
  start_url: string;
};

export const ssoApi = {
  info:      () => api<SsoInfo>("/auth/sso/info"),
  getConfig: () => api<SsoConfig>("/auth/sso/config"),
  putConfig: (body: SsoConfigUpdate) => api<SsoConfig>("/auth/sso/config", { method: "PUT", body: JSON.stringify(body) }),
};

export const meApi = {
  get:           () => api<AppUser>("/auth/me"),
  updateProfile: (body: { name?: string | null }) => api<AppUser>("/auth/me", { method: "PUT", body: JSON.stringify(body) }),
  changePassword:(current_password: string, new_password: string) =>
    api<void>("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  signOutEverywhere: () => api<void>("/auth/sign-out-everywhere", { method: "POST" }),
};
