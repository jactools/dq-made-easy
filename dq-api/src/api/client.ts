import axios from "axios";
import { getToken } from "../auth/token";

// import.meta.env may not be typed in all environments; access safely
const viteEnv = (
  typeof (import.meta as any) !== "undefined"
    ? (import.meta as any).env
    : undefined
) as Record<string, any> | undefined;
const nodeEnv =
  typeof globalThis !== "undefined" &&
  (globalThis as any).process &&
  (globalThis as any).process.env
    ? (globalThis as any).process.env
    : undefined;
const base =
  (viteEnv && viteEnv.VITE_API_URL) ||
  (nodeEnv && nodeEnv.VITE_API_URL) ||
  "/api";

export const api = axios.create({ baseURL: base });

// Attach in-memory token if present
api.interceptors.request.use((cfg) => {
  try {
    const t = getToken();
    if (t) {
      cfg.headers = cfg.headers || {};
      (cfg.headers as any)["Authorization"] = `Bearer ${t}`;
    }
  } catch (err) {
    console.warn("api request interceptor error:", err);
  }
  return cfg;
});
