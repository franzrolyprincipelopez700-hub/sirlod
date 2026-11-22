import { data } from "react-router";
import { api, ApiError, responseHeadersWithCookies } from "~/services/api.server";
import type { Demo, ModelGroup, Module, WorkspaceView } from "./types";

export async function activateVersion(request: Request, id: string) {
  if (!/^[\da-f-]{36}$/i.test(id)) throw new Response("Versión inválida", { status: 400 });
  return api.post(`/aprendizaje/modelos/${id}/activar`, request);
}

export async function loadWorkspace(request: Request, module: Module) {
  const { modelos } = await api.get("/aprendizaje/modelos", request) as { modelos: ModelGroup[] };
  const model = modelos.find((item) => item.modulo === module);
  if (!model) throw new Error("El módulo solicitado no está disponible");

  const query = new URL(request.url).searchParams;
  const selection = query.get("vista");
  const hasFilters = [...query.keys()].some((key) => key !== "vista");
  const view: WorkspaceView = selection === "practica" || (
    selection !== "operacion" && !hasFilters && !model.activo &&
    model.versiones.some((version) => version.modo === "demo" && version.algoritmo)
  ) ? "practica" : "operacion";

  let practice: Demo | null = null;
  let practiceError: string | null = null;
  if (view === "practica") {
    try {
      practice = await api.get(`/aprendizaje/demo/${module}`, request) as Demo;
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 409) throw error;
      const body = error.data as { errors?: { msg?: string }[] } | undefined;
      practiceError = body?.errors?.[0]?.msg ?? "La versión de práctica requiere entrenamiento.";
    }
  }
  return { model, view, practice, practiceError };
}

export function reply<T>(request: Request, payload: T, status = 200) {
  const headers = responseHeadersWithCookies(request);
  headers.set("Cache-Control", "no-store");
  return data(payload, { status, headers });
}

export function failure(request: Request, error: unknown) {
  if (error instanceof Response) throw error;
  if (error instanceof ApiError) {
    const body = error.data as { code?: string; errors?: { msg?: string }[] } | undefined;
    return reply(request, {
      ok: false as const,
      error: body?.errors?.[0]?.msg ?? error.message,
      code: body?.code,
    }, error.status);
  }
  return reply(request, { ok: false as const, error: "No se pudo completar la operación." }, 500);
}

export function validMutation(request: Request) {
  const site = request.headers.get("Sec-Fetch-Site");
  if (site === "cross-site") throw new Response("Solicitud de otro sitio", { status: 403 });
}

