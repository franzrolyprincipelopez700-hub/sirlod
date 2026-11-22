import { Form, Link, useLoaderData } from "react-router";
import { Button, Input, Select } from "~/shared/components/ui";
import { AnomalyPractice } from "./practice";
import { card, JsonDetails, label, localDate, Operation, Reason } from "./shared";
import type { Case, History, Policy } from "./types";
import { ModelDetails, Workspace, WorkspaceError } from "./workspace";

export { action, loader } from "./panel.server";
import type { loader } from "./panel.server";

const severities = [{ value: "ordinaria", label: "Ordinaria" }, { value: "grave", label: "Grave" }];

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
    <h3 className="font-semibold">#{incident.id} · {label(incident.tipo)} · {label(incident.estado)}</h3>
    <p className="text-sm">
      {localDate(incident.ocurrido)} · <Link className="underline" to={`?usuario=${incident.usuario_id}#expediente`}>
        {incident.codigo ?? `Usuario #${incident.usuario_id}`}
      </Link>{incident.gravedad && ` · Gravedad ${label(incident.gravedad)}`}
    </p>
    <JsonDetails label="Evidencias" value={incident.evidencia} />
    {incident.tipo === "anomalia" && incident.estado === "pendiente" && <Link className="text-sm underline"
      to={`?usuario=${incident.usuario_id}&alerta=${incident.id}#incidentes`}>Registrar hecho verificable asociado</Link>}
    {["pendiente", "confirmado"].includes(incident.estado) && <details className="space-y-2">
      <summary className="cursor-pointer text-sm font-medium">Revisar incidente</summary>
      <Operation intent="incidente-revision" id={incident.id} label="Guardar revisión"
        confirm="¿Registrar esta decisión en el historial?">
        <Select name="decision" label="Decisión" options={reviewOptions} />
        <Select name="gravedad" label="Gravedad al confirmar" options={severities} />
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
    <JsonDetails label="Auditoría autorizada de decisiones y correcciones" value={{
      decisiones: history.decisiones,
      medidasAnuladas: audit,
      incidentesAnulados: history.incidentes.filter((incident) => incident.estado === "anulado"),
      descargosDeMedidasAnuladas: history.descargos.filter((appeal) => audit.some((m) => m.id === appeal.medida_id)),
    }} />
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
        : <WorkspaceError message={data.practiceError ?? "La práctica no está disponible."} /> : <>
      <section id="incidentes" className="space-y-3">
        <h2 className="text-xl font-bold">Alertas e incidentes</h2>
        <div className={`${card} space-y-3`}>
          <Operation<{ disponible: boolean; alertas: number; muestras?: number; mensaje?: string }>
            intent="analizar" label="Analizar semanas recientes" view={(result) => <p className="text-sm">
              {result.mensaje ?? `${result.alertas} alertas nuevas de ${result.muestras} periodos por cuenta.`}
            </p>} />
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
          {data.incidentes.length === 0 && <p className="text-sm">No hay resultados para el filtro seleccionado.</p>}
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

