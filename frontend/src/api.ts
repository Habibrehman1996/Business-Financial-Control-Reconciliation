
export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function apiRequest<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const text = await response.text();

  let data: any = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!response.ok) {
    const message =
      typeof data === "object" && data?.detail
        ? typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail)
        : `API Error: ${response.status}`;

    throw new Error(message);
  }

  return data as T;
}

export function apiGet<T = unknown>(path: string): Promise<T> {
  return apiRequest<T>(path, {
    method: "GET",
  });
}

export function apiPost<T = unknown>(
  path: string,
  payload: unknown,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
export function apiPut<T = unknown>(
  path: string,
  payload: unknown,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
export function asArray(data: any): any[] {
  if (Array.isArray(data)) return data;

  if (data && typeof data === "object") {
    for (const key of ["items", "data", "results", "accounts", "rows"]) {
      if (Array.isArray(data[key])) {
        return data[key];
      }
    }
  }

  return [];
}

export function formatPKR(value: unknown): string {
  const amount = Number(value ?? 0);

  if (!Number.isFinite(amount)) return "Rs. 0";

  return new Intl.NumberFormat("en-PK", {
    style: "currency",
    currency: "PKR",
    maximumFractionDigits: 0,
  }).format(amount);
}
