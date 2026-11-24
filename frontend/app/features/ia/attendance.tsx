import { Form, Link, useLoaderData, type ActionFunctionArgs, type LoaderFunctionArgs } from "react-router";
import { api } from "~/services/api.server";
import { requireRole } from "~/services/auth.server";
import { Button, Input, Select } from "~/shared/components/ui";
import { dayLabel, Empty, integer, Panel, Ring, total } from "./charts";
import { activateVersion, failure, loadWorkspace, reply, validMutation, workspaceView } from "./learning.server";
import { AttendancePractice, Tag } from "./practice";
import { card, label, localDate, Operation, percent, Reason } from "./shared";
import type { AttendanceSlot, DashboardSummary, Risk } from "./types";
import { ModelDetails, Stat, Workspace, WorkspaceError } from "./workspace";

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
  if (admin && workspaceView(new URL(request.url).searchParams) === "practica") {
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

const attendanceColors: Record<string, string> = {
  asistio: "#178d75", inasistencia: "#ad6849", sin_verificar: "#9d732f", pendiente: "#3b79b2", cancelado: "#788795",
};

function AttendanceOverview({ summary }: { summary: DashboardSummary }) {
  const rows = summary.por_resultado ?? [];
  const count = (status: string) => rows.find((item) => item.clave === status)?.valor ?? 0;
  const verified = count("asistio") + count("inasistencia");
  return <>
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Stat label="Turnos registrados" value={integer.format(total(rows))} detail="Incluye confirmados y cancelados" />
      <Stat label="Resultados verificados" value={integer.format(verified)} detail="Asistencia o inasistencia documentada" />
      <Stat label="Tasa de asistencia" value={verified ? percent(count("asistio") / verified) : "—"} detail="Entre los turnos con resultado verificado" />
      <Stat label="Por verificar" value={integer.format(count("sin_verificar"))} detail="Turnos finalizados sin evidencia concluyente" />
    </dl>
    <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
      <Panel title="Resultados de asistencia" subtitle={dayLabel(summary.inicio) + " al " + dayLabel(summary.fin)}>
        <Ring label="turnos" data={Object.entries(attendanceColors).map(([key, color]) => ({ label: label(key), value: count(key), color }))} />
      </Panel>
      <Panel title="Del turno al registro" subtitle="Cada estado indica una acción distinta.">
        <ol className="space-y-3 text-sm">
          <li className="rounded-xl bg-blue-50 p-3"><strong>Pendiente</strong><p>{count("pendiente")} turnos aún por finalizar.</p></li>
          <li className="rounded-xl bg-amber-50 p-3"><strong>Sin verificar</strong><p>El turno terminó y falta comprobar el resultado.</p></li>
          <li className="rounded-xl bg-emerald-50 p-3"><strong>Verificado</strong><p>El resultado documentado alimenta futuras evaluaciones del modelo.</p></li>
        </ol>
      </Panel>
    </div>
  </>;
}

export default function Attendance() {
  const data = useLoaderData<typeof loader>();
  if (!data.ok) return <WorkspaceError message={data.error} />;
  const workspace = data.workspace;
  if (workspace) return <Workspace module="inasistencia" view={workspace.view}>
    {workspace.view === "practica" ? workspace.practice
      ? <AttendancePractice key={workspace.practice.version} data={workspace.practice} />
      : <WorkspaceError message={workspace.practiceError ?? "La evaluación no está disponible."} /> : <>
      {workspace.dashboard && <AttendanceOverview summary={workspace.dashboard} />}
      <AttendanceRecords data={data} riskAvailable={Boolean(workspace.model.activo && workspace.model.compatible)} />
    </>}
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

function AttendanceRecords({ data, riskAvailable = false }: {
  data: { admin: boolean; query: Record<string, string>; turnos: AttendanceSlot[] }; riskAvailable?: boolean;
}) {
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
        {riskAvailable ? <Operation<{ mensaje: string; alertas: (Risk & {
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
          </div>} /> : <p className="text-sm text-slate-600">
            La predicción por reserva requiere un modelo operativo activo.
            <Link className="ml-1 font-semibold underline" to="?vista=evaluacion">Explorar predicciones evaluadas</Link>
          </p>}
      </section>}
      <div>
        <h2 className="text-xl font-bold">Turnos y evidencias</h2>
        <p className="mt-1 text-sm text-slate-600">Consulta el registro de cada turno y comprueba su resultado.</p>
      </div>
      {data.turnos.length === 0 && <Empty>No hay turnos confirmados o cancelados para este filtro.</Empty>}
      <div className="grid gap-4 xl:grid-cols-2">
        {data.turnos.map((slot) => <article key={slot.detalle_id} className={`${card} space-y-3`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="font-bold text-slate-900">{slot.losa}</h3>
              <p className="text-sm text-slate-600">{dayLabel(slot.fecha)} · {slot.hora_inicio.slice(0, 5)}–{slot.hora_fin.slice(0, 5)}</p>
              <p className="text-xs text-slate-600">Permiso #{slot.permiso_id} · {slot.codigo ?? "Trabajador"}</p>
            </div>
            <Tag color={slot.resultado === "asistio" ? "green" : slot.resultado === "inasistencia" || slot.resultado === "sin_verificar" ? "amber" : "neutral"}>
              {label(slot.resultado)}
            </Tag>
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
          {data.admin && riskAvailable && slot.predecible && <Operation<Risk> intent="risk" id={slot.detalle_id} label="Calcular riesgo"
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

