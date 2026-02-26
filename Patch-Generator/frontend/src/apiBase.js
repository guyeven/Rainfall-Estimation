const envBase = import.meta.env.VITE_API_BASE_URL;
export const API_BASE = (typeof envBase === "string" && envBase.trim()) || "http://127.0.0.1:8000";
