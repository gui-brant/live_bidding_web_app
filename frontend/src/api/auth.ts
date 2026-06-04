import { API_BASE_URL, authStorage } from "./client";
import type { RegisterPayload, User, UserRole } from "./types";

const CURRENT_USER_KEY = "mock_current_user";
const PENDING_REGISTER_KEY = "pending_register_info";
const OTP_TTL_MS = 5 * 60 * 1000;

type OtpPurpose = "REGISTER" | "LOGIN";

type BackendRole = "rep" | "admin";

type BackendProfile = {
  user_id: string;
  email: string;
  role: BackendRole;
  display_name?: string | null;
};

type TokenResponse = {
  access_token?: string | null;
  expires_in: number;
  profile: BackendProfile;
};

type ErrorResponse = {
  detail?: string;
};

type PendingRegisterInfo = {
  email: string;
  display_name?: string;
  role?: UserRole;
};

function mapRole(role: BackendRole): UserRole {
  return role === "admin" ? "ADMIN" : "REP";
}

function readPendingRegister(email: string): PendingRegisterInfo | null {
  const raw = localStorage.getItem(PENDING_REGISTER_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as PendingRegisterInfo;
    if (parsed.email !== email) {
      return null;
    }
    return parsed;
  } catch (error) {
    console.warn("Failed to parse pending register info, clearing.", error);
    localStorage.removeItem(PENDING_REGISTER_KEY);
    return null;
  }
}

function writePendingRegister(info: PendingRegisterInfo) {
  localStorage.setItem(PENDING_REGISTER_KEY, JSON.stringify(info));
}

function clearPendingRegister() {
  localStorage.removeItem(PENDING_REGISTER_KEY);
}

function persistSession(profile: BackendProfile) {
  const pending = readPendingRegister(profile.email);
  const user: User = {
    id: profile.user_id,
    username: profile.email,
    role: mapRole(profile.role),
    email: profile.email,
    display_name: profile.display_name ?? pending?.display_name
  };
  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
  clearPendingRegister();
}

async function parseError(response: Response): Promise<Error> {
  try {
    const data = (await response.json()) as ErrorResponse;
    if (data?.detail) {
      return new Error(data.detail);
    }
  } catch {
    // Ignore parse errors for empty or non-JSON bodies.
  }
  return new Error("Request failed");
}

export function initMockUsersIfNeeded() {
  // TODO: remove mock init once backend is fully wired.
}

export function getCurrentUser(): User | null {
  const raw = localStorage.getItem(CURRENT_USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as User;
  } catch (error) {
    console.warn("Failed to parse current user, clearing.", error);
    localStorage.removeItem(CURRENT_USER_KEY);
    return null;
  }
}

async function fetchDevOtp(email: string): Promise<string | undefined> {
  if (!import.meta.env.DEV) {
    return undefined;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/dev/otp/${encodeURIComponent(email)}`, {
      credentials: "include"
    });
    if (!response.ok) {
      return undefined;
    }
    const data = (await response.json()) as { code?: string };
    return data.code;
  } catch (error) {
    console.warn("Failed to fetch dev OTP.", error);
    return undefined;
  }
}

export async function requestOtp(
  email: string,
  purpose: OtpPurpose,
  payload?: RegisterPayload
): Promise<{ expires_at: number; otp_dev?: string }> {
  if (purpose === "REGISTER" && payload) {
    writePendingRegister({
      email: payload.email,
      display_name: payload.display_name,
      role: payload.role
    });
  }

  const response = await fetch(`${API_BASE_URL}/auth/otp/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify({ email, purpose: purpose.toLowerCase() })
  });

  if (!response.ok && response.status !== 204) {
    throw await parseError(response);
  }

  const otpDev = await fetchDevOtp(email);
  return { expires_at: Date.now() + OTP_TTL_MS, otp_dev: otpDev };
}

export async function verifyOtp(
  email: string,
  otp: string,
  purpose: OtpPurpose
): Promise<{ access_token: string }> {
  // TODO: replace with backend calls later (already wired to backend endpoints).
  const pending = purpose === "REGISTER" ? readPendingRegister(email) : null;
  const rolePayload = pending?.role ? { role: pending.role.toLowerCase() } : {};
  const response = await fetch(`${API_BASE_URL}/auth/otp/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify({
      email,
      code: otp,
      purpose: purpose.toLowerCase(),
      ...(pending?.display_name ? { display_name: pending.display_name } : {}),
      ...rolePayload
    })
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  const data = (await response.json()) as TokenResponse;
  const token = data.access_token ?? "cookie-session";
  authStorage.setToken(token);
  persistSession(data.profile);

  if (purpose === "LOGIN") {
    return { access_token: token };
  }

  return { access_token: token };
}

export async function logout() {
  // TODO: replace with backend calls later (already wired to backend endpoints).
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include"
    });
  } catch (error) {
    console.warn("Logout request failed.", error);
  } finally {
    authStorage.clearToken();
    localStorage.removeItem(CURRENT_USER_KEY);
    clearPendingRegister();
  }
}
