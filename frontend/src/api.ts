export interface Session {
  accessToken: string;
  userId: string;
  expiresAt: string;
  sessionWarningSeconds: number;
}
export interface Config {
  authenticationMode: string;
  push: { available: boolean; publicKey: string | null };
}
export interface Preferences {
  enabled: boolean;
  intervals: number[];
  availableIntervals: number[];
}
interface Document {
  id: string;
  status: string;
  issuedOn: string | null;
  expiresOn: string | null;
  cachedAt: string;
  isCurrent: boolean;
}
export interface Licence extends Document {
  expiryKind: string;
  categories: { code: string; expiresOn: string | null }[];
}
export interface Check {
  id: string;
  requestedAt: string;
  outcome: string;
  outcomeLabel: string;
  isLatestSuccessful: boolean;
  statusChanged: boolean | null;
  sourceLabel: string;
  error: { code: string; message: string } | null;
}
export interface Driving {
  renewalActions: ("renew_licence" | "renew_medical")[];
  status: string;
  statusLabel: string;
  reasonCodes: string[];
  explanations: string[];
  lastUpdatedAt: string | null;
  isStale: boolean;
  nextExpiryDate: string | null;
  nextExpiryIsStale: boolean;
  medicalRequirement: string;
  licences: Licence[];
  medicalCertificates: Document[];
  latestCheck: Check | null;
  warnings: { code: string; message: string }[];
}
export interface Guidance {
  actions: { code: string; title: string; description: string }[];
  externalNotice: string;
  fallbackMessage: string;
  officialUrl: string;
}
export interface Notice {
  id: string;
  sentAt: string;
  documentLabel: string;
  expiresOn: string;
  daysBefore: number;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  token = "",
  method = "GET",
  body?: unknown,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch("/api/v1" + path, {
      method,
      cache: "no-store",
      headers: {
        "Accept-Language": "en",
        ...(token && { Authorization: "Bearer " + token }),
        ...(body !== undefined && { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      "CONNECTION_FAILED",
      "Cannot reach the service. Check your connection and try again.",
    );
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      data?.error?.code || "SERVICE_UNAVAILABLE",
      data?.error?.message || "The service is unavailable. Please try again.",
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
export function errorText(e: unknown) {
  return e instanceof ApiError
    ? e.message + " (" + e.code + ")"
    : "The action could not be completed. Please try again. (ACTION_FAILED)";
}
export const scenarios = [
  "Valid licence",
  "Expiring licence",
  "Expired licence",
  "Invalid entitlement",
  "Registry unavailable",
  "Slow registry",
  "Expiring medical certificate",
];
export function date(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(value + "T12:00:00"))
    : "Unavailable";
}
export function time(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "No successful update yet";
}
export function reminderDate(value: string | null, lead: number) {
  if (!value) return null;
  const d = new Date(value + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - lead);
  return date(d.toISOString().slice(0, 10));
}

export function daysLeft(value: string) {
  return (
    Math.floor(Date.parse(value) / 86400000) - Math.floor(Date.now() / 86400000)
  );
}
