import { apiRequest } from "./client";
import { getCurrentUser } from "./auth";
import type { User } from "./types";

type BackendMe = {
  user_id: string;
  email: string;
  role: "rep" | "admin";
  display_name?: string | null;
};

const CURRENT_USER_KEY = "mock_current_user";

function mapRole(role: "rep" | "admin"): User["role"] {
  return role === "admin" ? "ADMIN" : "REP";
}

export async function getMe(): Promise<User> {
  const data = await apiRequest<BackendMe>({
    path: "/me",
    options: { method: "GET" },
    mock: () => {
      const raw = localStorage.getItem(CURRENT_USER_KEY);
      if (!raw) {
        throw new Error("No current user");
      }
      const cached = JSON.parse(raw) as User;
      return {
        user_id: cached.id,
        email: cached.email ?? cached.username,
        role: cached.role === "ADMIN" ? "admin" : "rep",
        display_name: cached.display_name,
      };
    },
  });

  const user: User = {
    id: data.user_id,
    username: data.email,
    role: mapRole(data.role),
    email: data.email,
    display_name: data.display_name ?? undefined,
  };

  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
  return user;
}
