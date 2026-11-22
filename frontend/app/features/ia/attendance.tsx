import { Form, useLoaderData, type ActionFunctionArgs, type LoaderFunctionArgs } from "react-router";
import { api } from "~/services/api.server";
import { requireRole } from "~/services/auth.server";
import { Button, Input, Select } from "~/shared/components/ui";
import { activateVersion, failure, loadWorkspace, reply, validMutation } from "./learning.server";
import { AttendancePractice } from "./practice";
import { card, label, localDate, Operation, percent, Reason } from "./shared";
import type { AttendanceSlot, Risk } from "./types";
import { ModelDetails, Workspace, WorkspaceError } from "./workspace";

export async function loader({ request }: LoaderFunctionArgs) {
  const admin = new URL(request.url).pathname.startsWith("/dashboard/");
  await requireRole(request, "trabajador", admin ? "Administrador" : "Seguridad");
  const query = new URL(request.url).searchParams;
  try {
    const workspace = admin ? await loadWorkspace(request, "inasistencia") : null;
    const filters = new URLSearchParams(query);
    filters.delete("vista");
    const result = workspace?.view === "practica" ? { turnos: [] } :
      await api.get(`/aprendizaje/asistencias?${filters}`, request) as { turnos: AttendanceSlot[] };
    return reply(request, { ok: true as const, admin, workspace, query: Object.fromEntries(query), ...result });
  } catch (error) {
    return failure(request, error);
  }
}

export async function action({ request }: ActionFunctionArgs) {
  const admin = new URL(request.url).pathname.startsWith("/dashboard/");
  await requireRole(request, "trabajador", admin ? "Administrador" : "Seguridad");
  validMutation(request);
  if (admin && new URL(request.url).searchParams.get("vista") === "practica") {
    throw new Response("Las decisiones operativas requieren la vista Operación", { status: 400 });
  }
  const form = await request.formData();
  const intent = form.get("intent");
  if (admin && intent === "activar") {
    try {
      return reply(request, { ok: true as const, result: await activateVersion(request, String(form.get("id") ?? "")) });
    } catch (error) {
      return failure(request, error);
    }
  }
  const id = Number(form.get("id"));
  const queue = admin && intent === "risk-queue";
  if (!queue && (!Number.isSafeInteger(id) || id <= 0 || (intent !== "attendance" && !(admin && intent === "risk")))) {
    throw new Response("Operación inválida", { status: 400 });
  }
  try {
    const result = queue ? await api.post("/aprendizaje/riesgo", request) : intent === "risk"
      ? await api.post(`/aprendizaje/riesgo/${id}`, request)
      : await api.post(`/aprendizaje/asistencias/${id}`, request,
          { resultado: form.get("resultado"), evidencia: form.get("evidencia") });
    return reply(request, { ok: true as const, result });
  } catch (error) {
    return failure(request, error);
  }
}

export default function Attendance() {
  const data = useLoaderData<typeof loader>();
  if (!data.ok) return <WorkspaceError message={data.error} />;
  const workspace = data.workspace;
  if (workspace) return <Workspace module="inasistencia" view={workspace.view}>
    {workspace.view === "practica" ? workspace.practice
      ? <AttendancePractice key={workspace.practice.version} data={workspace.practice} />
      : <WorkspaceError message={workspace.practiceError ?? "La práctica no está disponible."} /> :
      <AttendanceRecords data={data} />}
    <ModelDetails model={workspace.model} view={workspace.view} />
  </Workspace>;
  return <div className="space-y-4">
    <header>
      <h1 className="text-2xl font-bold">Registro de asistencia</h1>
      <p className="text-sm text-[var(--text-muted)]">Registra el resultado de cada turno confirmado después de su cierre.</p>
    </header>
    <AttendanceRecords data={data} />
  </div>;
}

function AttendanceRecords({ data }: { data: { admin: boolean; query: Record<string, string>; turnos: AttendanceSlot[] } }) {
  const { query } = data;
  const offset = Number(query.offset ?? 0);
  return <div className="space-y-4">
    <Form method="get" className={`${card} flex flex-wrap items-end gap-3`}>
      {data.admin && <input type="hidden" name="vista" value="operacion" />}
      <Input label="Desde" type="date" name="inicio" defaultValue={query.inicio} />
      <Input label="Hasta" type="date" name="fin" defaultValue={query.fin} />
      <Input label="Código de usuario" name="codigo" maxLength={15} defaultValue={query.codigo} />
      <Button type="submit" size="sm">Filtrar turnos</Button>
    </Form>
      {data.admin && <section className={`${card} space-y-3`}>
        <h2 className="font-semibold">Seguimiento preventivo</h2>
        <Operation<{ mensaje: string; alertas: (Risk & {
          detalle_id: number; permiso_id: number; losa: string; fecha: string; hora: string;
        })[] }> intent="risk-queue" label="Evaluar turnos de los próximos 7 días"
          view={(result) => <div className="space-y-2 text-sm">
            <p>{result.mensaje}</p>
            <ul className="divide-y divide-[var(--border-color)]">
              {result.alertas.map((alert) => <li className="py-2" key={alert.detalle_id}>
                <strong>{alert.losa} · {alert.fecha} · {alert.hora.slice(0, 5)} · {percent(alert.riesgo ?? 0)}</strong>
                <p>Permiso #{alert.permiso_id} · {alert.mensaje}</p>
              </li>)}
            </ul>
          </div>} />
      </section>}
      {data.turnos.length === 0 && <p className={card}>No hay turnos confirmados o cancelados para este filtro.</p>}
      <div className="grid gap-4 xl:grid-cols-2">
        {data.turnos.map((slot) => <article key={slot.detalle_id} className={`${card} space-y-3`}>
          <div>
            <h2 className="font-semibold">{slot.losa} · {slot.fecha} · {slot.hora_inicio.slice(0, 5)}–{slot.hora_fin.slice(0, 5)}</h2>
            <p className="text-sm">Turno #{slot.detalle_id} · Permiso #{slot.permiso_id} · {slot.codigo ?? "Trabajador"} · {label(slot.resultado)}</p>
          </div>
          {slot.evidencia && slot.registrado && <p className="text-sm break-words">{slot.evidencia} · {localDate(slot.registrado)} · Personal #{slot.actor_id}</p>}
          {data.admin && slot.asistencia_id && slot.resultado === "inasistencia" && slot.usuario_id && (
            <a className="text-sm underline" href={`/dashboard/anomalias?vista=operacion&asistencia=${slot.asistencia_id}&usuario=${slot.usuario_id}#incidentes`}>
              Abrir incidente documentado
            </a>
          )}
          {slot.registrable && <details className="space-y-2">
            <summary className="cursor-pointer text-sm font-medium">{slot.asistencia_id ? "Corregir registro" : "Registrar resultado"}</summary>
            <Operation intent="attendance" id={slot.detalle_id} label="Guardar asistencia"
              confirm={slot.asistencia_id ? "¿Registrar una corrección de asistencia con esta evidencia?" : "¿Guardar este resultado de asistencia?"}>
              <Select label="Resultado" name="resultado" required defaultValue={slot.resultado} options={[
                { value: "sin_verificar", label: "Sin verificar" }, { value: "asistio", label: "Asistió" },
                { value: "inasistencia", label: "Inasistencia comprobada" },
              ]} />
              <Reason name="evidencia" label="Evidencia verificable o motivo de corrección" />
            </Operation>
          </details>}
          {data.admin && slot.predecible && <Operation<Risk> intent="risk" id={slot.detalle_id} label="Calcular riesgo"
            view={(risk) => <p className="text-sm">
              {risk.disponible && risk.riesgo !== undefined && <strong>Riesgo {risk.nivel} · {percent(risk.riesgo)}. </strong>}
              {risk.mensaje}
            </p>} />}
        </article>)}
      </div>
      {(offset > 0 || data.turnos.length === 100) && <Form method="get" className="flex gap-2">
        {Object.entries(query).filter(([key]) => key !== "offset").map(([key, value]) =>
          <input key={key} type="hidden" name={key} value={value} />)}
        {offset > 0 && <Button type="submit" name="offset" value={Math.max(0, offset - 100)} size="sm">Anterior</Button>}
        {data.turnos.length === 100 && <Button type="submit" name="offset" value={offset + 100} size="sm">Siguiente</Button>}
      </Form>}
  </div>;
}

