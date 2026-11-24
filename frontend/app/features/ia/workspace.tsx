import type { ReactNode } from "react";
import { FaCalendarAlt, FaChartLine, FaClipboardCheck, FaFlask, FaShieldAlt } from "react-icons/fa";
import { Link } from "react-router";
import { decimal, Empty, integer } from "./charts";
import { card, label, localDate, Operation, percent } from "./shared";
import type { ModelGroup, Module, Version, WorkspaceView } from "./types";
import "./analytics.css";

const workspaces = {
  demanda: {
    title: "Demanda de losas",
    description: "Identifica las horas de mayor uso y consulta qué turnos están libres.",
    icon: FaChartLine,
  },
  anomalias: {
    title: "Alertas de actividad",
    description: "Consulta patrones de reserva y documenta las decisiones de revisión.",
    icon: FaShieldAlt,
  },
  inasistencia: {
    title: "Asistencia y riesgo",
    description: "Revisa los resultados registrados y prioriza el seguimiento de los próximos turnos.",
    icon: FaClipboardCheck,
  },
};

export function Workspace({ module, view, children }: {
  module: Module; view?: WorkspaceView; children: ReactNode;
}) {
  const { title, description, icon: Icon } = workspaces[module];
  return <div className="ml-page min-w-0 space-y-5" data-module={module}>
    <header className="ml-hero">
      <div className="ml-kicker"><Icon aria-hidden="true" /> Analítica de reservas</div>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
    {view && <div>
      <nav aria-label="Vistas de análisis" className="ml-tabs">
        {([{ key: "operacion", name: "Operación", icon: FaCalendarAlt }, {
          key: "practica", name: "Evaluación del modelo", icon: FaFlask,
        }] as const).map(({ key, name, icon: ModeIcon }) =>
          <Link key={key} to={key === "operacion" ? "?" : "?vista=evaluacion"}
            aria-current={view === key ? "page" : undefined}>
            <ModeIcon aria-hidden="true" />{name}
          </Link>)}
      </nav>
    </div>}
    {view === "practica" && <p className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
      La evaluación ejecuta el modelo entrenado sobre un conjunto sintético de validación. Las decisiones y evidencias se registran en <Link to="?" className="font-semibold underline">Operación</Link>.
    </p>}
    {children}
  </div>;
}

export function WorkspaceError({ message }: { message: string }) {
  return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{message}</div>;
}

export function Stat({ label: title, value, detail }: { label: string; value: ReactNode; detail: string }) {
  return <div className="ml-stat">
    <dt>{title}</dt>
    <dd>{value}</dd>
    <dd>{detail}</dd>
  </div>;
}

const metrics = [
  { key: "brier", title: "Error Brier", detail: "Más bajo indica probabilidades más precisas", ratio: false },
  { key: "roc_auc", title: "ROC-AUC", detail: "Capacidad para diferenciar ambos resultados", ratio: false },
  { key: "roc_auc_demo", title: "ROC-AUC en evaluación", detail: "Separación de casos sintéticos", ratio: false },
  { key: "f1", title: "F1", detail: "Equilibrio entre precisión y sensibilidad", ratio: false },
  { key: "precision", title: "Precisión", detail: "Aciertos entre las predicciones positivas", ratio: true },
  { key: "recall", title: "Sensibilidad", detail: "Casos positivos detectados", ratio: true },
  { key: "tasa_alertas", title: "Tasa de alertas", detail: "Muestras por encima del umbral", ratio: true },
  { key: "sensibilidad_perturbacion", title: "Sensibilidad a cambios", detail: "Respuesta a actividad alterada en la prueba", ratio: true },
];

function readable(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? decimal.format(value) : "—";
}

function Partitions({ version }: { version: Version }) {
  const rows = version.evaluacion.particiones;
  if (!Array.isArray(rows) || !rows.length) return null;
  const names = rows.length === 4
    ? ["Entrenamiento", "Calibración", "Validación", "Prueba"]
    : ["Entrenamiento", "Validación", "Prueba"];
  return <details className="space-y-3 rounded-xl border border-slate-200 px-4 py-3 text-sm">
    <summary className="cursor-pointer font-semibold">Particiones por fecha</summary>
    <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {rows.map((part, i) => <div key={names[i] ?? i} className="ml-evidence">
        <dt>{names[i]}</dt>
        <dd className="my-1 font-semibold">{readable(part.n)} ejemplos</dd>
        {part.inicio && part.fin && <dd className="text-xs">{localDate(part.inicio)} – {localDate(part.fin)}</dd>}
      </div>)}
    </dl>
  </details>;
}

function VersionDetails({ version, allowActivation }: { version: Version; allowActivation: boolean }) {
  const values = version.evaluacion.prueba;
  const candidates = version.evaluacion.validacion;
  const matrix = values?.matriz_confusion;
  const calibration = values?.calibracion;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="font-bold text-slate-900">{version.algoritmo ?? label(version.estado)}</p>
        <p className="text-sm text-slate-600">{integer.format(version.evaluacion.total ?? 0)} ejemplos · {localDate(version.creado)}</p></div>
      <span className="text-xs text-slate-600" title={version.version}>Versión {version.version.slice(0, 8)}</span>
    </div>
    {version.evaluacion.motivo && <p className="text-sm text-slate-700">{version.evaluacion.motivo}</p>}
    {values && <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {metrics.map(({ key, title, detail, ratio }) => {
        const value = values[key];
        return typeof value === "number" && <Stat key={key} label={title} detail={detail} value={ratio ? percent(value) : readable(value)} />;
      })}
    </dl>}
    {Array.isArray(matrix) && matrix.length === 2 && matrix.every((row) => Array.isArray(row) && row.length === 2) &&
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="ml-evidence">
          <h3 className="mb-2 text-sm font-bold">Matriz de confusión</h3>
          <table className="w-full text-sm">
            <thead><tr><th scope="col" className="text-left">Observado</th><th scope="col">Previó no</th><th scope="col">Previó sí</th></tr></thead>
            <tbody>{matrix.map((row, i) => <tr key={i} className="border-t border-slate-200">
              <th scope="row" className="py-1.5 text-left font-medium">{i ? "Sí" : "No"}</th>
              {row.map((value: unknown, j: number) => <td key={j} className="py-1.5 text-center font-semibold">{readable(value)}</td>)}
            </tr>)}</tbody>
          </table>
        </div>
        {Array.isArray(calibration) && <div className="ml-evidence">
          <h3 className="mb-2 text-sm font-bold">Probabilidad estimada y frecuencia observada</h3>
          <ul className="space-y-1.5 text-sm">{calibration.map((row, i) => <li key={i} className="flex justify-between gap-2">
            <span>Estimó {percent(row.predicho)}</span><strong>Ocurrió {percent(row.observado)}</strong>
          </li>)}</ul>
        </div>}
      </div>}
    {candidates !== null && typeof candidates === "object" && <details className="space-y-2 text-sm">
      <summary className="cursor-pointer font-semibold">Comparación de algoritmos</summary>
      <ul className="divide-y divide-slate-200">
        {Object.entries(candidates).map(([method, result]) => <li key={method} className="flex flex-wrap justify-between gap-2 py-2">
          <strong>{method}</strong>
          <span>{typeof result.brier === "number"
            ? "Error Brier " + readable(result.brier)
            : "Sensibilidad a cambios " + (typeof result.sensibilidad_perturbacion === "number" ? percent(result.sensibilidad_perturbacion) : "—")}</span>
        </li>)}
      </ul>
    </details>}
    <Partitions version={version} />
    {allowActivation && version.modo === "real" && version.estado === "evaluado" && !version.activo &&
      <Operation intent="activar" id={version.version} label="Habilitar versión operativa"
        confirm="¿Habilitar esta versión para las predicciones operativas de SIRLOD?" />}
  </div>;
}

export function ModelDetails({ model, view }: { model: ModelGroup; view: WorkspaceView }) {
  const lab = view === "practica";
  const versions = model.versiones.filter((version) => version.modo === (lab ? "demo" : "real"));
  const current = lab ? versions[0] : model.activo ?? versions[0];
  const status = model.activo && !lab ? (model.compatible ? "Activo" : "Requiere reentrenamiento")
    : current ? label(current.estado) : "Sin modelo operativo activo";
  const others = versions.filter((version) => version.version !== current?.version);
  return <details className={card + " ml-panel space-y-4"} open={lab || undefined}>
    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 font-semibold [&::-webkit-details-marker]:hidden">
      <span className="inline-flex items-center gap-2"><FaChartLine className="text-[#1B6EB6]" aria-hidden="true" /> {lab ? "Resultados del entrenamiento" : "Estado del modelo operativo"}</span>
      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">{status}</span>
    </summary>
    {!lab && <p className="text-sm text-slate-600">{integer.format(model.predicciones_registradas)} predicciones operativas registradas. <Link to="?vista=evaluacion" className="font-semibold underline">Consultar evaluación</Link></p>}
    {current ? <VersionDetails version={current} allowActivation={!lab} /> : <Empty>
      El modelo operativo requiere historial institucional suficiente y una evaluación aprobada.
    </Empty>}
    {others.length > 0 && <details className="space-y-2">
      <summary className="cursor-pointer text-sm font-semibold">Versiones anteriores</summary>
      {others.map((version) => <details key={version.version} className="space-y-2 rounded-lg border border-slate-200 p-3">
        <summary className="cursor-pointer text-sm">{localDate(version.creado)} · {label(version.estado)}</summary>
        <VersionDetails version={version} allowActivation={!lab} />
      </details>)}
    </details>}
  </details>;
}
