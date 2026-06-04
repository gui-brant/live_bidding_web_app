export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "access_token";

export const authStorage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => localStorage.removeItem(TOKEN_KEY)
};

type RequestOptions = {
  method?: string;
  body?: unknown;
  credentials?: RequestCredentials;
};

type RequestContext<T> = {
  path: string;
  options?: RequestOptions;
  mock: () => Promise<T> | T;
};

type ApiError = Error & { skipMock?: boolean };

function redirectToLogin() {
  if (window.location.pathname !== "/auth") {
    window.location.href = "/auth";
  }
}

export async function apiRequest<T>({ path, options, mock }: RequestContext<T>): Promise<T> {
  const token = authStorage.getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json"
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options?.method ?? "GET",
      headers,
      body: options?.body ? JSON.stringify(options.body) : undefined,
      credentials: options?.credentials ?? "include"
    });

    if (response.status === 401) {
      authStorage.clearToken();
      redirectToLogin();
      const error: ApiError = new Error("Unauthorized");
      error.skipMock = true;
      throw error;
    }

    if (!response.ok) {
      if (response.status >= 500) {
        console.warn(`API ${path} failed with ${response.status}, using mock.`);
        return await Promise.resolve(mock());
      }
      const error: ApiError = new Error(`Request failed: ${response.status}`);
      error.skipMock = true;
      throw error;
    }

    return response.json();
  } catch (error) {
    const apiError = error as ApiError;
    if (apiError?.skipMock) {
      throw error;
    }
    console.warn(`Network error calling ${path}, using mock.`, error);
    return await Promise.resolve(mock());
  }
}
