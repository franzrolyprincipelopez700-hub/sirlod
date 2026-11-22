import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { api, ApiError, responseHeadersWithCookies } from "~/services/api.server";

const browserRoutes: Record<string, RegExp> = {
  GET: /^permisos\/(?:detalles\/[1-9]\d*|[1-9]\d*\/documento)$/,
  POST: /^(?:imagenes\/upload|chatbot(?:\/conversacion|\/)?|auth\/(?:forgot-password|reset-password))$/,
  DELETE: /^imagenes\/[1-9]\d*$/,
};

function errorResponse(message: string, status: number) {
  return Response.json({ message }, { status, headers: { "Cache-Control": "no-store" } });
}

async function forward({ request, params }: ActionFunctionArgs | LoaderFunctionArgs) {
  const path = params["*"] ?? "";
  const method = request.method;
  if (!browserRoutes[method]?.test(path)) return errorResponse("Ruta no disponible", 404);
  const url = new URL(request.url);
  const origin = request.headers.get("Origin");
  if (method !== "GET" && (request.headers.get("Sec-Fetch-Site") === "cross-site" || (origin && origin !== url.origin))) {
    return errorResponse("Origen de solicitud inválido", 403);
  }

  const endpoint = `/${path}${url.search}`;
  try {
    let result: unknown;
    if (method === "GET") {
      result = await api.get(endpoint, request);
    } else if (method === "DELETE") {
      result = await api.delete(endpoint, request);
    } else {
      const multipart = path === "imagenes/upload";
      let payload: unknown;
      try {
        payload = multipart ? await request.formData() : await request.json();
      } catch {
        return errorResponse("El contenido de la solicitud es inválido", 400);
      }
      result = multipart ? await api.postForm(endpoint, request, payload as FormData) : await api.post(endpoint, request, payload, path === "chatbot/conversacion" ? 30_000 : undefined);
    }
    const headers = responseHeadersWithCookies(request);
    headers.set("Cache-Control", "no-store");
    return Response.json(result ?? null, { headers });
  } catch (error) {
    if (error instanceof Response) throw error;
    if (error instanceof ApiError) {
      const headers = responseHeadersWithCookies(request);
      headers.set("Cache-Control", "no-store");
      return Response.json(error.data ?? { message: error.message }, { status: error.status, headers });
    }
    return errorResponse("No se pudo completar la operación", 502);
  }
}

export const loader = forward;
export const action = forward;
