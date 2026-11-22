import { useLoaderData, type ActionFunctionArgs, type LoaderFunctionArgs } from "react-router";
import { api } from "~/services/api.server";
import { requireRole } from "~/services/auth.server";
import { failure, reply, validMutation } from "./learning.server";
import { card, label, localDate, Operation, Reason } from "./shared";
import type { History } from "./types";

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "usuario");
  try {
    return reply(request, { ok: true as const, result: await api.get("/aprendizaje/mi-situacion", request) as History });
  } catch (error) {
    return failure(request, error);
  }
}

export async function action({ request }: ActionFunctionArgs) {
  await requireRole(request, "usuario");
  validMutation(request);
  const form = await request.formData();
  const id = Number(form.get("id"));
  if (form.get("intent") !== "descargo" || !Number.isSafeInteger(id) || id <= 0) {
    throw new Response("Operación inválida", { status: 400 });
  }
  try {
    const result = await api.post(`/aprendizaje/mi-situacion/${id}/descargos`, request, { texto: form.get("texto") });
    return reply(request, { ok: true as const, result });
  } catch (error) {
    return failure(request, error);
  }
}

export default function Situation() {
  const data = useLoaderData<typeof loader>();
  return <div className="space-y-4">
    <h1 className="text-2xl font-bold">Mi situación</h1>
    {!data.ok ? <p role="alert">{data.error}</p> : <>
      <p className="text-sm">Infracciones válidas registradas: {data.result.infracciones_validas}</p>
      {data.result.medidas.length === 0 && <p className={card}>No tienes medidas registradas.</p>}
      {data.result.medidas.map((measure) => {
        const appeals = data.result.descargos.filter((appeal) => appeal.medida_id === measure.id);
        return <article key={measure.id} className={`${card} space-y-3`}>
          <h2 className="text-lg font-semibold">{label(measure.tipo)} · {label(measure.estado)}</h2>
          <p>{measure.motivo}</p>
          <p className="text-sm">Inicio {localDate(measure.inicio)}{measure.fin && ` · Fin ${localDate(measure.fin)}`}</p>
          {appeals.map((appeal) => <div key={appeal.id} className="rounded-lg bg-[var(--bg-surface)] p-3 text-sm">
            <p>{localDate(appeal.creado)} · {appeal.texto}</p>
            <p className="font-medium">{appeal.decision ?? "Pendiente de revisión"}</p>
          </div>)}
          {!appeals.some((appeal) => !appeal.decision) && <Operation intent="descargo" id={measure.id}
            label="Presentar descargo" message="Descargo enviado para revisión.">
            <Reason name="texto" label="Justificación o descargo" />
          </Operation>}
        </article>;
      })}
    </>}
  </div>;
}

