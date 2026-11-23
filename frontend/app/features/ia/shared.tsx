import type { ReactNode } from "react";
import { useFetcher } from "react-router";
import { Button, Input } from "~/shared/components/ui";

export const card = "rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] shadow-sm p-4 md:p-5";

export const percent = (value: number) => new Intl.NumberFormat("es-PE", {
  style: "percent", maximumFractionDigits: 1,
}).format(value);

export const localDate = (value: string) => new Intl.DateTimeFormat("es-PE", {
  dateStyle: "medium", timeStyle: "short", timeZone: "America/Lima",
}).format(new Date(value));

export const campusDate = new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Lima" });

const labels: Record<string, string> = {
  asistio: "Asistió", inasistencia: "Inasistencia", sin_verificar: "Sin verificar",
  pendiente: "Pendiente", cancelado: "Cancelado", confirmado: "Confirmado",
  descartado: "Descartado", anulado: "Anulado", derivado: "Derivado", preventiva: "Restricción preventiva",
  advertencia: "Advertencia", suspension: "Suspensión", confirmada: "Confirmada",
  cumplida: "Cumplida", levantada: "Levantada", anulada: "Anulada",
  anomalia: "Alerta estadística", otro: "Incidente documentado",
  ordinaria: "Ordinaria", grave: "Grave", evaluado: "Evaluado",
  insuficiente: "Datos insuficientes", rechazado: "Evaluación insuficiente",
  modelo_real: "Modelo real", frecuencia_historica: "Frecuencia histórica",
  disponibilidad: "Disponibilidad",
};
export const label = (value: string) => labels[value] ?? value;

export function Reason({ name = "motivo", label: fieldLabel = "Motivo documentado" }) {
  return <Input required minLength={8} maxLength={2000} name={name} label={fieldLabel} />;
}

export function Operation<T = unknown>({ intent, id, label: buttonLabel, confirm, children, view, message }: {
  intent: string;
  id?: string | number;
  label: string;
  confirm?: string;
  children?: ReactNode;
  view?: (data: T) => ReactNode;
  message?: string;
}) {
  const fetcher = useFetcher<{ ok: true; result: T } | { ok: false; error: string }>();
  return (
    <fetcher.Form method="post" className="space-y-2" onSubmit={(event) => {
      if (confirm && !window.confirm(confirm)) event.preventDefault();
    }}>
      <input type="hidden" name="intent" value={intent} />
      {id !== undefined && <input type="hidden" name="id" value={id} />}
      {children}
      <Button type="submit" size="sm" loading={fetcher.state !== "idle"}>{buttonLabel}</Button>
      {fetcher.data?.ok === false && <p className="text-sm text-red-600" role="alert">{fetcher.data.error}</p>}
      {fetcher.data?.ok && (view
        ? <div aria-live="polite">{view(fetcher.data.result)}</div>
        : <p className="text-sm text-emerald-700" role="status">{message ?? "Cambios registrados."}</p>)}
    </fetcher.Form>
  );
}
