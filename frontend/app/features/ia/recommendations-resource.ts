import type { LoaderFunctionArgs } from "react-router";
import { api } from "~/services/api.server";
import { requireRole } from "~/services/auth.server";
import { failure, reply } from "./learning.server";
import type { Demand } from "./types";

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "usuario");
  const query = new URL(request.url).searchParams;
  const params = new URLSearchParams({ fecha: query.get("fecha") ?? "", tipo: query.get("tipo") ?? "Normal" });
  if (query.has("disciplina")) params.set("disciplina", query.get("disciplina") ?? "");
  try {
    const result = await api.get(`/aprendizaje/recomendaciones?${params}`, request) as Demand;
    return reply(request, { ok: true as const, query: params.toString(), result });
  } catch (error) {
    return failure(request, error);
  }
}

