import type { ReactNode } from "react";
import { FaCalendarAlt, FaChartLine, FaClipboardCheck, FaFlask, FaShieldAlt } from "react-icons/fa";
import { Link } from "react-router";
import { card, JsonDetails, label, localDate, Operation } from "./shared";
import type { ModelGroup, Module, Version, WorkspaceView } from "./types";

const workspaces = {
  demanda: {
    title: "Demanda de losas",
    description: "Consulta la ocupación por turno y encuentra las franjas con menor demanda.",
    icon: FaChartLine,
  },
  anomalias: {
    title: "Alertas de actividad",
    description: "Revisa patrones de reserva inusuales, evidencias y decisiones administrativas.",
    icon: FaShieldAlt,
  },
  inasistencia: {
    title: "Asistencia y riesgo",
    description: "Consulta qué turnos requieren seguimiento y revisa los resultados de asistencia.",
    icon: FaClipboardCheck,
  },
};

export function Workspace({ module, view, children }: {
  module: Module; view?: WorkspaceView; children: ReactNode;
}) {
  const { title, description, icon: Icon } = workspaces[module];
  return <div className="min-w-0 space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-6 rounded-2xl bg-linear-to-br from-[#112a45] to-[#175283] p-5 text-white shadow-sm sm:p-7">
      <div className="flex min-w-0 items-start gap-4">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-white/20 bg-white/10 text-sky-100 sm:size-13">
          <Icon size={21} aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-[1.9rem]">{title}</h1>
          <p className="mt-1 max-w-lg text-sm leading-relaxed text-blue-100">{description}</p>
        </div>
      </div>
      {view && <nav aria-label="Entorno de trabajo" className="inline-flex rounded-xl border border-white/20 bg-black/15 p-1">
        {([{ key: "practica", name: "Práctica", icon: FaFlask }, {
          key: "operacion", name: "Operación", icon: FaCalendarAlt,
        }] as const).map(({ key, name, icon: ModeIcon }) =>
          <Link key={key} to={`?vista=${key}`} aria-current={view === key ? "page" : undefined}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
              view === key ? "bg-white text-[#153e61] shadow-sm" : "text-blue-100 hover:bg-white/10 hover:text-white"
            }`}>
            <ModeIcon size={12} aria-hidden="true" />{name}
          </Link>)}
      </nav>}
    </header>
    {view === "practica" && <div className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-[#224e72]">
      <FaFlask size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
      <p><strong>Entorno de práctica.</strong> Los casos y las acciones de esta vista son de prueba y están aislados de la operación.</p>
    </div>}
    {children}
  </div>;
}

export function WorkspaceError({ message }: { message: string }) {
  return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{message}</div>;
}

export function Stat({ label: title, value, detail }: { label: string; value: ReactNode; detail: string }) {
  return <div className="min-w-0 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] px-4 py-3.5 shadow-xs">
    <dt className="text-sm font-medium text-[var(--text-secondary)]">{title}</dt>
    <dd className="mt-1 text-2xl font-semibold tracking-tight text-[var(--text-primary)] tabular-nums">{value}</dd>
    <dd className="mt-0.5 text-xs text-[var(--text-secondary)]">{detail}</dd>
  </div>;
}

const metrics: Record<string, string> = {
  brier: "Error Brier", roc_auc: "ROC-AUC", f1: "F1", precision: "Precisión",
  recall: "Sensibilidad", tasa_alertas: "Tasa de alertas", sensibilidad_perturbacion: "Detección de perturbaciones",
};

function VersionDetails({ version, allowActivation }: { version: Version; allowActivation: boolean }) {
  const values = version.evaluacion.prueba;
  return <div className="space-y-3">
    <p className="text-sm text-[var(--text-secondary)]">
      {version.algoritmo ?? "Sin estimador"} · {version.evaluacion.total.toLocaleString("es-PE")} ejemplos · {localDate(version.creado)}
    </p>
    {version.evaluacion.motivo && <p className="text-sm">{version.evaluacion.motivo}</p>}
    {values && <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {Object.entries(metrics).map(([key, name]) => {
        const value = values[key];
        return typeof value === "number" && <div key={key} className="rounded-lg bg-[var(--bg-surface)] p-2.5">
          <dt className="text-xs text-[var(--text-secondary)]">{name}</dt>
          <dd className="font-semibold tabular-nums">{value.toFixed(3)}</dd>
        </div>;
      })}
    </dl>}
    <JsonDetails label="Ver evaluación y particiones" value={version.evaluacion} />
    <p className="break-all font-mono text-xs text-[var(--text-secondary)]">Versión {version.version}</p>
    {allowActivation && version.modo === "real" && version.estado === "evaluado" && !version.activo &&
      <Operation intent="activar" id={version.version} label="Habilitar versión operativa"
        confirm="¿Habilitar esta versión para las predicciones operativas de SIRLOD?" />}
  </div>;
}

export function ModelDetails({ model, view }: { model: ModelGroup; view: WorkspaceView }) {
  const versions = model.versiones.filter((version) => version.modo === (view === "practica" ? "demo" : "real"));
  const current = view === "operacion" ? model.activo ?? versions[0] : versions[0];
  const status = view === "practica" ? (current ? label(current.estado) : "Pendiente de entrenamiento") :
    model.activo ? (model.compatible ? "Activo" : "Requiere reentrenamiento") : "Sin modelo operativo activo";
  const others = versions.filter((version) => version.version !== current?.version);
  return <details className={`${card} space-y-4`}>
    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 font-semibold [&::-webkit-details-marker]:hidden">
      <span className="inline-flex items-center gap-2"><FaChartLine className="text-[#1B6EB6]" aria-hidden="true" /> Modelo y evaluación</span>
      <span className="rounded-full bg-[var(--bg-surface)] px-3 py-1 text-xs text-[var(--text-secondary)]">{status}</span>
    </summary>
    {view === "operacion" && <p className="text-sm text-[var(--text-secondary)]">Predicciones registradas: {model.predicciones_registradas}</p>}
    {current && <VersionDetails version={current} allowActivation={view === "operacion"} />}
    {others.length > 0 && <details className="space-y-2">
      <summary className="cursor-pointer text-sm font-semibold">Versiones anteriores</summary>
      {others.map((version) => <details key={version.version} className="space-y-2 rounded-lg border border-[var(--border-color)] p-3">
        <summary className="cursor-pointer text-sm">{localDate(version.creado)} · {label(version.estado)}</summary>
        <VersionDetails version={version} allowActivation={view === "operacion"} />
      </details>)}
    </details>}
  </details>;
}
