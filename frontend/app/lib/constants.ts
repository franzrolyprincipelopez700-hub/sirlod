export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "/api/servicio";

const hostingUploadLimit = Number(import.meta.env.VITE_MAX_UPLOAD_MB);

export function uploadLimitMb(applicationLimit: number): number {
  return Number.isFinite(hostingUploadLimit) && hostingUploadLimit > 0
    ? Math.min(hostingUploadLimit, applicationLimit)
    : applicationLimit;
}
