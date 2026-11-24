import { Form, Link, useLoaderData } from "react-router";
import { Button, Input, Select } from "~/shared/components/ui";
import { Empty, HorizontalBars, integer, Panel, Ring, total } from "./charts";
import { AnomalyPractice, Tag } from "./practice";
import { card, label, localDate, Operation, Reason } from "./shared";
import type { Case, DashboardSummary, History, Policy } from "./types";
import { ModelDetails, Stat, Workspace, WorkspaceError } from "./workspace";

export { action, loader } from "./panel.server";
import type { loader } from "./panel.server";

const severities = [{ value: "ordinaria", label: "Ordinaria" }, { value: "grave", label: "Grave" }];

const evidenceNames: Record<string, string> = {
  registro: "Registro verificable", referencia: "Referencia documentada",
  puntuacion: "Puntuación de rareza", umbral: "Umbral del modelo",
  periodo_fin_exclusivo: "Cierre de la semana analizada",
  solicitudes: "Solicitudes", cancelaciones: "Cancelaciones", intentos: "Intentos",
  intentos_rechazados: "Intentos rechazados", repeticiones_franja: "Repeticiones de franja",
  solicitudes_media_previa: "Promedio previo de solicitudes", norma_id: "Regla registrada",
  horas: "Horas", verificacion: "Verificación",
};

function Evidence({ value }: { value: Record<string, unknown> }) {
  const features = value.variables;
  const fields = Object.entries({
    ...value, ...(features && typeof features === "object" && !Array.isArray(features) ? features : {}),
  }).flatMap(([key, item]) => {
    if (typeof item === "number") return [{ key, text: item.toLocaleString("es-PE", { maximumFractionDigits: 3 }) }];
    if (typeof item !== "string" || !item.trim()) return [];
    return [{ key, text: key === "periodo_fin_exclusivo" && Number.isFinite(Date.parse(item)) ? localDate(item) : item }];
  });
  return fields.length ? <dl className="ml-evidence grid gap-3 sm:grid-cols-2">
    {fields.map(({ key, text }) => <div key={key} className={text.length > 50 ? "sm:col-span-2" : ""}>
      <dt>{evidenceNames[key] ?? key.replaceAll("_", " ")}</dt><dd>{text}</dd>
    </div>)}
  </dl> : null;
}

function Overview({ data, policies }: { data: DashboardSummary; policies: Policy[] }) {
  const all = data.casos ?? [];
  const statuses = ["pendiente", "confirmado", "descartado", "derivado", "anulado"].map((state) => ({
    label: label(state), value: all.filter((item) => item.estado === state).reduce((sum, item) => sum + item.cantidad, 0),
  }));
  const requests = data.por_solicitud ?? [];
  const alerts = all.filter((item) => item.tipo === "anomalia").reduce((sum, item) => sum + item.cantidad, 0);
  return <>
    <dl className="grid gap-3 sm:grid-cols-3">
      <Stat label="En revisión" value={integer.format(statuses[0].value)} detail="Alertas o incidentes pendientes" />
      <Stat label="Alertas del modelo" value={integer.format(alerts)} detail="Alertas estadísticas registradas" />
      <Stat label="Reglas vigentes" value={policies.filter((item) => item.vigente).length} detail="Requeridas para aplicar medidas" />
    </dl>
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Actividad observada" subtitle="Solicitudes e intentos registrados en los últimos 28 días">
        <HorizontalBars label="Actividad del periodo" data={[
          { label: "Solicitudes", value: total(requests) },
          { label: "Cancelaciones", value: requests.find((row) => row.clave === "Cancelado")?.valor ?? 0 },
          { label: "Intentos registrados", value: data.intentos ?? 0 },
        ]} />
      </Panel>
      <Panel title="Estado de los expedientes" subtitle="Alertas estadísticas e incidentes documentados">
        <Ring data={statuses} label="registros" />
      </Panel>
    </div>
  </>;
}

function CaseCard({ incident, policies }: { incident: Case; policies: Policy[] }) {
  const eligible = policies.filter((p) => p.vigente && p.tipo === incident.tipo &&
    p.gravedad === (incident.gravedad ?? "ordinaria") &&
    (incident.estado === "pendiente" ? p.medida === "preventiva" : incident.estado === "confirmado" && p.medida !== "preventiva"));
  const reviewOptions = incident.estado === "confirmado"
    ? [{ value: "anular", label: "Anular infracción" }]
    : [
        ...(incident.tipo === "anomalia" ? [] : [{ value: "confirmar", label: "Confirmar infracción" }]),
        { value: "descartar", label: "Descartar" },
      ];
  return <article className={`${card} space-y-3`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-bold text-slate-900">{label(incident.tipo)} · #{incident.id}</h3>
      <Tag color={incident.estado === "pendiente" ? "amber" : incident.estado === "confirmado" ? "blue" : "neutral"}>
        {label(incident.estado)}
      </Tag>
    </div>
    <p className="text-sm">
      {localDate(incident.ocurrido)} · <Link className="underline" to={`?usuario=${incident.usuario_id}#expediente`}>
        {incident.codigo ?? `Usuario #${incident.usuario_id}`}
      </Link>{incident.gravedad && ` · Gravedad ${label(incident.gravedad)}`}
    </p>
    <Evidence value={incident.evidencia} />
    {incident.tipo === "anomalia" && incident.estado === "pendiente" && <Link className="text-sm underline"
      to={`?usuario=${incident.usuario_id}&alerta=${incident.id}#incidentes`}>Registrar incidente asociado con evidencia</Link>}
    {["pendiente", "confirmado"].includes(incident.estado) && <details className="space-y-2">
      <summary className="cursor-pointer rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm font-semibold">
        {incident.estado === "confirmado" ? "Corregir o anular decisión" : incident.tipo === "anomalia" ? "Revisar o descartar alerta" : "Confirmar o descartar incidente"}
      </summary>
      <Operation intent="incidente-revision" id={incident.id} label="Registrar decisión"
        confirm="¿Registrar esta decisión en el historial?">
        <Select name="decision" label="Decisión" options={reviewOptions} />
        {incident.tipo !== "anomalia" && incident.estado === "pendiente" &&
          <Select name="gravedad" label="Gravedad al confirmar" options={severities} />}
        <Reason />
        <Reason name="evidencia" label="Verificación documentada" />
      </Operation>
    </details>}
    {eligible.length > 0 && <details className="space-y-2">
      <summary className="cursor-pointer text-sm font-medium">Aplicar medida autorizada</summary>
      <Operation intent="medida" id={incident.id} label="Aplicar medida"
        confirm="¿Aplicar la medida a este usuario y dejar constancia de la decisión?">
        <Select name="norma_id" label="Regla aprobada" options={eligible.map((rule) => ({
          value: rule.id, label: `#${rule.id} · ${label(rule.medida)} · ${rule.minimo_previas} previas`,
        }))} />
        <Input name="horas" label="Duración en horas (si restringe reservas)" min={1} type="number" />
        <Reason />
        <Reason name="verificacion" label="Evidencia de cumplimiento del criterio" />
      </Operation>
    </details>}
  </article>;
}

function Dossier({ user, history }: { user: number; history: History }) {
  const valid = history.medidas.filter((measure) => measure.estado !== "anulada");
  const audit = history.medidas.filter((measure) => measure.estado === "anulada");
  return <section id="expediente" className={`${card} space-y-4`}>
    <h2 className="text-xl font-bold">Expediente del usuario #{user}</h2>
    <p>Infracciones válidas: <strong>{history.infracciones_validas}</strong></p>
    {history.incidentes.filter((incident) => incident.estado === "confirmado").map((incident) =>
      <p key={incident.id} className="text-sm">#{incident.id} · {label(incident.tipo)} · {localDate(incident.ocurrido)}</p>)}
    {valid.length === 0 && <p className="text-sm">Sin medidas válidas.</p>}
    {valid.map((measure) => <article key={measure.id} className="space-y-2 border-t border-[var(--border-color)] pt-3">
      <h3 className="font-semibold">#{measure.id} · {label(measure.tipo)} · {label(measure.estado)}</h3>
      <p className="text-sm">{measure.motivo} · {localDate(measure.inicio)}{measure.fin && ` – ${localDate(measure.fin)}`}</p>
      <details className="space-y-2">
        <summary className="cursor-pointer text-sm font-medium">Revisar medida</summary>
        <Operation intent="medida-revision" id={measure.id} label="Registrar revisión"
          confirm="¿Aplicar esta revisión? La anulación de una sanción corrige también la infracción asociada.">
          <Select name="decision" label="Decisión" options={[
            ...(measure.estado === "confirmada" ? [{ value: "levantar", label: "Levantar / desbloquear" }] : []),
            { value: "anular", label: "Anular por error" },
          ]} />
          <Reason />
        </Operation>
      </details>
      {history.descargos.filter((appeal) => appeal.medida_id === measure.id).map((appeal) =>
        <div key={appeal.id} className="rounded-lg bg-[var(--bg-surface)] p-3 text-sm space-y-2">
          <p>Descargo #{appeal.id} · {localDate(appeal.creado)}</p>
          <p>{appeal.texto}</p>
          {appeal.decision ? <p>Revisión: {appeal.decision}</p> :
            <Operation intent="descargo-revision" id={appeal.id} label="Resolver descargo"
              confirm="¿Registrar esta resolución del descargo?">
              <Reason name="texto" label="Resolución documentada" />
            </Operation>}
        </div>)}
    </article>)}
    <details className="space-y-3 border-t border-slate-200 pt-3 text-sm">
      <summary className="cursor-pointer font-semibold">Auditoría de decisiones y correcciones</summary>
      {history.decisiones.length === 0 && <Empty>Aún no hay decisiones auditadas.</Empty>}
      <ol className="divide-y divide-slate-100">
        {history.decisiones.map((decision) => <li key={decision.id} className="space-y-1 py-3">
          <strong>{label(decision.accion.replaceAll("_", " "))} · Incidente #{decision.incidente_id}</strong>
          <p className="text-xs text-slate-600">{localDate(decision.creado)} · Responsable #{decision.actor_id}</p>
          <p>{decision.motivo}</p><Evidence value={decision.datos} />
        </li>)}
      </ol>
      {audit.map((measure) => <div key={measure.id} className="ml-evidence">
        <p><strong>Medida anulada #{measure.id}</strong> · {label(measure.tipo)}</p>
        <p>{measure.motivo}</p>
        {history.descargos.filter((appeal) => appeal.medida_id === measure.id).map((appeal) =>
          <p key={appeal.id}>Descargo registrado · {appeal.decision ?? appeal.texto}</p>)}
      </div>)}
      {history.incidentes.filter((item) => item.estado === "anulado").map((item) => (
        <p key={item.id}>Infracción anulada #{item.id} · {localDate(item.ocurrido)}</p>
      ))}
    </details>
  </section>;
}

function Policies({ items }: { items: Policy[] }) {
  return <section id="normativa" className={`${card} space-y-4`}>
    <h2 className="text-xl font-bold">Normativa configurable</h2>
    {items.length === 0 && <p className="text-sm">No hay reglas institucionales registradas. La aplicación de medidas está deshabilitada.</p>}
    <details className="space-y-2">
      <summary className="cursor-pointer font-medium">Registrar borrador de regla</summary>
      <Operation intent="norma" label="Guardar borrador">
        <div className="grid gap-2 md:grid-cols-3">
          <Select name="tipo" label="Tipo de incidente" options={[
            { value: "inasistencia", label: "Inasistencia verificada" }, { value: "otro", label: "Otro hecho documentado" },
          ]} />
          <Select name="gravedad" label="Gravedad" options={severities} />
          <Select name="medida" label="Medida" options={["advertencia", "preventiva", "suspension"].map(
            (value) => ({ value, label: label(value) }))} />
          <Input name="minimo_previas" label="Mínimo de infracciones válidas previas" type="number" min={0} defaultValue={0} required />
          <Input name="maximo_horas" label="Máximo de horas si restringe reservas" type="number" min={1} />
          <Reason name="fundamento" label="Fundamento y referencia institucional" />
        </div>
        <Reason name="criterio" label="Condiciones objetivas de aplicación" />
      </Operation>
    </details>
    {items.map((rule) => <details key={rule.id} className="border-t border-[var(--border-color)] pt-3 space-y-2">
      <summary className="cursor-pointer text-sm font-medium">
        #{rule.id} · {label(rule.medida)} · {label(rule.tipo)} · {rule.minimo_previas} previas · {rule.vigente ? "Vigente" : rule.aprobada ? "Retirada" : "Pendiente de aprobación"}
      </summary>
      <p className="text-sm">{rule.fundamento} · {rule.criterio}{rule.aprobacion && ` · ${rule.aprobacion}`}</p>
      {(rule.vigente || !rule.aprobada) && <Operation intent="norma-revision" id={rule.id}
        label={rule.vigente ? "Retirar regla" : "Activar regla aprobada"}
        confirm={rule.vigente ? "¿Retirar esta regla para decisiones nuevas?" : "¿Confirmas que existe un instrumento institucional de aprobación? "}>
        <input type="hidden" name="vigente" value={String(!rule.vigente)} />
        <Reason name="fundamento" label={rule.vigente ? "Motivo del retiro" : "Instrumento oficial de aprobación"} />
      </Operation>}
    </details>)}
  </section>;
}

export default function AnomalyWorkspace() {
  const data = useLoaderData<typeof loader>();
  const filters = data.ok ? data.query : {};
  const offset = Number(filters.offset ?? 0);
  return <Workspace module="anomalias" view={data.ok ? data.view : undefined}>
    {!data.ok ? <WorkspaceError message={data.error} /> : <>
      {data.view === "practica" ? data.practice
        ? <AnomalyPractice key={data.practice.version} data={data.practice} />
        : <WorkspaceError message={data.practiceError ?? "La evaluación no está disponible."} /> : <>
      {data.dashboard && <Overview data={data.dashboard} policies={data.normas} />}
      <section id="incidentes" className="space-y-3">
        <h2 className="text-xl font-bold">Bandeja de revisión</h2>
        <p className="text-sm text-slate-600">Abre la evidencia de un caso y registra la decisión en su expediente.</p>
        <div className={`${card} space-y-3`}>
          {data.model.activo && data.model.compatible ? <Operation<{ disponible: boolean; alertas: number; muestras?: number; mensaje?: string }>
            intent="analizar" label="Analizar semanas recientes" view={(result) => <p className="text-sm">
              {result.mensaje ?? `${result.alertas} alertas nuevas de ${result.muestras} periodos por cuenta.`}
            </p>} /> : <p className="text-sm text-slate-600">
              El análisis automático requiere un modelo operativo activo.
              <Link className="ml-1 font-semibold underline" to="?vista=evaluacion">Explorar la evaluación del modelo</Link>.
            </p>}
          <details open={Boolean(filters.asistencia || filters.alerta) || undefined} className="space-y-2">
            <summary className="cursor-pointer font-medium">Registrar incidente con evidencia</summary>
            <Operation intent="incidente" label="Registrar incidente">
              <Input type="number" min={1} name="usuario_id" label="ID interno del usuario" defaultValue={filters.usuario} required />
              <Input type="number" min={1} name="asistencia_id" label="Registro de inasistencia (si corresponde)" defaultValue={filters.asistencia} />
              <Input name="referencia_hecho" label="Referencia del acta o registro para otros hechos" minLength={8} maxLength={2000} />
              <Input type="datetime-local" name="ocurrido" label="Fecha del hecho en hora de Lima (opcional)" />
              <Reason name="evidencia" label="Hecho y fuente verificable" />
              {filters.alerta && <input type="hidden" name="alerta_id" value={filters.alerta} />}
            </Operation>
          </details>
        </div>
        <Form method="get" className={`${card} flex flex-wrap items-center gap-3`}>
          <Input name="codigo" label="Código de usuario" defaultValue={filters.codigo} maxLength={15} />
          <Select name="estado" label="Estado" defaultValue={filters.estado ?? ""} options={[
            { value: "", label: "Expedientes y alertas" },
            ...["pendiente", "confirmado", "descartado", "derivado", "anulado"].map((value) => ({ value, label: label(value) })),
          ]} />
          <Button type="submit" size="sm">Buscar incidentes</Button>
        </Form>
        <div className="grid gap-3 xl:grid-cols-2">
          {data.incidentes.length === 0 && <Empty>No hay incidentes para el filtro seleccionado.</Empty>}
          {data.incidentes.map((incident) => <CaseCard key={incident.id} incident={incident} policies={data.normas} />)}
        </div>
        {(offset > 0 || data.incidentes.length === 100) && <Form method="get" className="flex gap-2">
          <input type="hidden" name="estado" value={filters.estado ?? ""} />
          <input type="hidden" name="codigo" value={filters.codigo ?? ""} />
          {offset > 0 && <Button type="submit" name="offset" value={Math.max(0, offset - 100)} size="sm">Anterior</Button>}
          {data.incidentes.length === 100 && <Button type="submit" name="offset" value={offset + 100} size="sm">Siguiente</Button>}
        </Form>}
      </section>
      {data.history && data.user ? <Dossier user={data.user} history={data.history} /> :
        <Form id="expediente" method="get" className={`${card} flex flex-wrap items-center gap-3`}>
          <Input name="usuario" label="ID interno del usuario" type="number" min={1} required />
          <Button type="submit" size="sm">Consultar expediente</Button>
        </Form>}
      <Policies items={data.normas} />
      </>}
      <ModelDetails model={data.model} view={data.view} />
    </>}
  </Workspace>;
}
