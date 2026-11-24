import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { api } from "~/services/api.server";
import { requireRole } from "~/services/auth.server";
import { activateVersion, failure, loadWorkspace, reply, validMutation, workspaceView } from "./learning.server";
import type { Case, History, Policy } from "./types";

const base = "/aprendizaje";

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  const query = new URL(request.url).searchParams;
  const filters = new URLSearchParams();
  for (const key of ["estado", "codigo", "offset"]) {
    const value = query.get(key);
    if (value) filters.set(key, value);
  }
  const id = Number(query.get("usuario"));
  const user = Number.isSafeInteger(id) && id > 0 ? id : null;
  try {
    const workspace = await loadWorkspace(request, "anomalias");
    const [incidents, policies, history] = workspace.view === "operacion" ? await Promise.all([
      api.get(`${base}/incidentes?${filters}`, request) as Promise<{ incidentes: Case[] }>,
      api.get(`${base}/normas`, request) as Promise<{ normas: Policy[] }>,
      user ? api.get(`${base}/expedientes/${user}`, request) as Promise<History> : Promise.resolve(null),
    ]) : [{ incidentes: [] }, { normas: [] }, null];
    return reply(request, {
      ok: true as const, ...workspace, ...incidents, ...policies, history, user, query: Object.fromEntries(query),
    });
  } catch (error) {
    return failure(request, error);
  }
}

export async function action({ request }: ActionFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  validMutation(request);
  if (workspaceView(new URL(request.url).searchParams) === "practica") {
    throw new Response("Las decisiones operativas requieren la vista Operación", { status: 400 });
  }
  const form = await request.formData();
  const field = (name: string) => String(form.get(name) ?? "");
  const integer = (name: string) => form.get(name) ? Number(form.get(name)) : null;
  const id = field("id");
  const numeric = /^\d+$/.test(id);
  const post = (path: string, payload?: unknown) => api.post(`${base}${path}`, request, payload);
  let result: unknown;
  try {
    switch (field("intent")) {
      case "activar":
        result = await activateVersion(request, id);
        break;
      case "demanda":
        result = await post(`/demanda?${new URLSearchParams({ fecha: field("fecha") })}`);
        break;
      case "analizar":
        result = await post("/anomalias");
        break;
      case "incidente":
        result = await post("/incidentes", {
          usuario_id: integer("usuario_id"), asistencia_id: integer("asistencia_id"),
          alerta_id: integer("alerta_id"), evidencia: field("evidencia"),
          ocurrido: field("ocurrido") ? `${field("ocurrido")}:00-05:00` : null,
          referencia_hecho: field("referencia_hecho") || null,
        });
        break;
      case "incidente-revision":
        if (!numeric) throw new Response("Incidente inválido", { status: 400 });
        result = await post(`/incidentes/${id}/revision`, {
          decision: field("decision"), motivo: field("motivo"), evidencia: field("evidencia"),
          gravedad: field("gravedad") || "ordinaria",
        });
        break;
      case "norma":
        result = await post("/normas", {
          tipo: field("tipo"), gravedad: field("gravedad"), medida: field("medida"),
          minimo_previas: integer("minimo_previas"), maximo_horas: integer("maximo_horas"),
          fundamento: field("fundamento"), criterio: field("criterio"),
        });
        break;
      case "norma-revision":
        if (!numeric) throw new Response("Norma inválida", { status: 400 });
        result = await post(`/normas/${id}/revision`, {
          vigente: field("vigente") === "true", fundamento: field("fundamento"),
        });
        break;
      case "medida":
        if (!numeric) throw new Response("Incidente inválido", { status: 400 });
        result = await post(`/incidentes/${id}/medidas`, {
          norma_id: integer("norma_id"), horas: integer("horas"), motivo: field("motivo"),
          verificacion: field("verificacion"),
        });
        break;
      case "medida-revision":
        if (!numeric) throw new Response("Medida inválida", { status: 400 });
        result = await post(`/medidas/${id}/revision`, { decision: field("decision"), motivo: field("motivo") });
        break;
      case "descargo-revision":
        if (!numeric) throw new Response("Descargo inválido", { status: 400 });
        result = await post(`/descargos/${id}/revision`, { texto: field("texto") });
        break;
      default:
        throw new Response("Operación inválida", { status: 400 });
    }
    return reply(request, { ok: true as const, result });
  } catch (error) {
    return failure(request, error);
  }
}

