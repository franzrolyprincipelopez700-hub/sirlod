import { useState, type ReactNode } from "react";
import { FaArrowRight, FaCalendarCheck, FaExclamationTriangle, FaSlidersH } from "react-icons/fa";
import { Button, Input, Select } from "~/shared/components/ui";
import { Panel, Ring } from "./charts";
import { card, percent } from "./shared";
import { Stat } from "./workspace";
import type { Demo, PracticeCase } from "./types";

const dateFormat = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short", year: "numeric", timeZone: "America/Lima" });
const numberFormat = new Intl.NumberFormat("es-PE", { maximumFractionDigits: 3 });
const dateLabel = (date: string) => dateFormat.format(new Date(date + "T12:00:00Z"));
const hourLabel = (hour: number) => `${String(hour).padStart(2, "0")}:00`;
const slotLabel = (row: PracticeCase) => `${hourLabel(Number(row.variables.hora))}–${hourLabel(Number(row.variables.hora) + 1)}`;
const courtLabel = (row: PracticeCase) => `Losa ${String(row.variables.losa).padStart(2, "0")}`;
const disciplines: Record<string, string> = { "1": "Vóley", "2": "Futsal", "3": "Básquet" };
const sport = (row: PracticeCase) => disciplines[String(row.variables.disciplina)] ?? "Multiuso";
const distinct = (values: string[]) => [...new Set(values)].sort();
const tone = {
  neutral: "bg-slate-100 text-slate-700",
  blue: "bg-blue-50 text-blue-800",
  amber: "bg-amber-50 text-amber-900",
  green: "bg-emerald-50 text-emerald-800",
};

export function Tag({ children, color = "neutral" }: { children: ReactNode; color?: keyof typeof tone }) {
  return <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${tone[color]}`}>{children}</span>;
}

export function DataTable({ title, columns, rows }: {
  title: string; columns: string[]; rows: { id: string | number; cells: ReactNode[] }[];
}) {
  if (!rows.length) return <p className="rounded-xl border border-dashed border-slate-300 px-4 py-7 text-center text-sm text-slate-600">
    No hay resultados para estos filtros.
  </p>;
  return <div className="max-h-[31rem] overflow-auto rounded-xl border border-[var(--border-color)]"
    role="region" aria-label={title} tabIndex={0}>
    <table className="w-full min-w-max text-left text-sm">
      <caption className="sr-only">{title}</caption>
      <thead className="sticky top-0 z-1 bg-slate-50 text-xs font-semibold text-slate-600">
        <tr>{columns.map((column) => <th key={column} scope="col" className="px-3.5 py-3">{column}</th>)}</tr>
      </thead>
      <tbody className="divide-y divide-[var(--border-color)]">
        {rows.map(({ id, cells }) => <tr key={id} className="hover:bg-slate-50/70">
          {cells.map((cell, index) => index === 0
            ? <th scope="row" className="px-3.5 py-3 font-semibold" key={index}>{cell}</th>
            : <td className="px-3.5 py-3" key={index}>{cell}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}

function Days({ days, day, onChange, label = "Fecha" }: {
  days: string[]; day: string; onChange: (day: string) => void; label?: string;
}) {
  return <Select label={label} value={day} onChange={(event) => onChange(event.target.value)}
    options={days.map((value) => ({ value, label: dateLabel(value) }))} />;
}

export function DemandPractice({ data }: { data: Demo }) {
  const days = distinct(data.muestras.map((row) => row.fecha));
  const [day, setDay] = useState(days.at(-1) ?? "");
  const [court, setCourt] = useState("");
  const courts = distinct(data.muestras.map((row) => String(row.variables.losa)));
  const slots = data.muestras.filter((row) => row.fecha === day && (!court || String(row.variables.losa) === court));
  const available = slots.filter((row) => row.objetivo === 0).sort((a, b) => a.puntuacion - b.puntuacion);
  const hours = [...new Set(slots.map((row) => Number(row.variables.hora)))].sort((a, b) => a - b);
  const average = (rows: PracticeCase[]) => rows.reduce((total, row) => total + row.puntuacion, 0) / Math.max(1, rows.length);
  return <div className="space-y-4">
    <section className={`${card} flex flex-wrap items-end gap-4`} aria-label="Filtros de demanda">
      <Days days={days} day={day} onChange={setDay} />
      <Select label="Losa deportiva" value={court} onChange={(event) => setCourt(event.target.value)} options={[
        { value: "", label: "Todas las losas" }, ...courts.map((value) => ({ value, label: `Losa ${value.padStart(2, "0")}` })),
      ]} />
    </section>
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Stat label="Turnos evaluados" value={slots.length} detail="Para la fecha y la losa seleccionadas" />
      <Stat label="Turnos libres" value={available.length} detail="Según la disponibilidad del caso" />
      <Stat label="Demanda estimada" value={slots.length ? percent(average(slots)) : "—"} detail="Promedio del modelo por turno" />
    </dl>
    <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
      <section className={`${card} space-y-4`}>
        <h2 className="text-lg font-semibold">Demanda por franja</h2>
        <ul className="space-y-2" aria-label="Demanda media por hora">
          {hours.map((hour) => {
            const value = average(slots.filter((row) => Number(row.variables.hora) === hour));
            return <li key={hour} className="grid grid-cols-[3rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-xs tabular-nums">
              <span className="text-slate-600">{hourLabel(hour)}</span>
              <div aria-hidden="true" className="h-2.5 rounded-full bg-blue-50">
                <div className="h-full rounded-full bg-[#2476b6]" style={{ width: `${value * 100}%` }} />
              </div>
              <span className="text-right font-semibold">{percent(value)}</span>
            </li>;
          })}
        </ul>
      </section>
      <section className={`${card} space-y-3`}>
        <h2 className="text-lg font-semibold">Alternativas recomendadas</h2>
        {available.length === 0 && <p className="text-sm text-slate-600">No hay franjas libres en este caso.</p>}
        <ul className="space-y-2">
          {available.slice(0, 3).map((row) => <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50/70 p-3">
            <div><p className="text-sm font-semibold">{courtLabel(row)} · {sport(row)}</p><p className="text-xs text-slate-600">{slotLabel(row)}</p></div>
            <Tag color="green">{percent(row.puntuacion)} de demanda</Tag>
          </li>)}
        </ul>
      </section>
    </div>
    <section className={`${card} space-y-3`}>
      <h2 className="text-lg font-semibold">Detalle de turnos</h2>
      <DataTable title="Detalle de turnos" columns={["Losa", "Disciplina", "Horario", "Disponibilidad", "Demanda"]}
        rows={slots.map((row) => ({ id: row.id, cells: [
          courtLabel(row), sport(row), slotLabel(row), row.objetivo ? <Tag>Ocupado</Tag> : <Tag color="green">Libre</Tag>, percent(row.puntuacion),
        ] }))} />
    </section>
  </div>;
}

const activity = {
  solicitudes: "Solicitudes",
  cancelaciones: "Cancelaciones",
  intentos: "Intentos",
  intentos_rechazados: "Intentos rechazados",
  repeticiones_franja: "Repeticiones de franja",
  solicitudes_media_previa: "Promedio previo de solicitudes",
};

export function AnomalyPractice({ data }: { data: Demo }) {
  const weeks = distinct(data.muestras.map((row) => row.fecha));
  const [week, setWeek] = useState(weeks.at(-1) ?? "");
  const [account, setAccount] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const threshold = data.umbrales.umbral;
  const alerted = (row: PracticeCase) => threshold !== undefined && row.puntuacion > threshold;
  const rows = data.muestras.filter((row) => row.fecha === week && row.cuenta?.toLowerCase().includes(account.trim().toLowerCase()))
    .sort((a, b) => b.puntuacion - a.puntuacion);
  const active = rows.find((row) => row.id === selected) ?? rows[0];
  const unusual = rows.filter(alerted).length;
  return <div className="space-y-4">
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Stat label="Cuentas evaluadas" value={rows.length} detail="Para la semana y la búsqueda actuales" />
      <Stat label="Por encima del umbral" value={unusual} detail="Patrones que el modelo marca para análisis" />
      <Stat label="Umbral del modelo" value={threshold === undefined ? "—" : numberFormat.format(threshold)} detail="Puntuación de rareza, no probabilidad" />
    </dl>
    {threshold !== undefined && <Panel title="Patrones de la semana" subtitle="Clasificación por puntuación de rareza">
      <Ring label="Cuentas" data={[
        { label: "Patrón habitual", value: rows.length - unusual, color: "#16766e" },
        { label: "Patrón inusual", value: unusual, color: "#bb6d20" },
      ]} />
    </Panel>}
    <div className="grid items-start gap-4 xl:grid-cols-[1.35fr_1fr]">
      <section className={`${card} min-w-0 space-y-4`}>
        <h2 className="text-lg font-semibold">Actividad por cuenta</h2>
        <div className="flex flex-wrap items-end gap-3">
          <Days days={weeks} day={week} onChange={setWeek} label="Semana desde" />
          <Input label="Buscar cuenta" value={account} onChange={(event) => setAccount(event.target.value)} placeholder="Ej. C-1408" />
        </div>
        <DataTable title="Actividad por cuenta" columns={["Cuenta", "Rareza", "Estado", "Evidencia"]}
          rows={rows.map((row) => ({ id: row.id, cells: [
            row.cuenta, numberFormat.format(row.puntuacion),
            alerted(row) ? <Tag color="amber">Inusual</Tag> : <Tag>Habitual</Tag>,
            <button type="button" onClick={() => setSelected(row.id)} aria-pressed={active?.id === row.id}
              className="inline-flex items-center gap-1.5 font-semibold text-[#175b91] hover:underline"
              aria-label={`Ver evidencia de ${row.cuenta}`}>Ver <FaArrowRight size={10} aria-hidden="true" /></button>,
          ] }))} />
      </section>
      {active && <section className={`${card} space-y-4`} aria-live="polite">
        <div className="flex items-start gap-3">
          <FaExclamationTriangle className="mt-1.5 text-amber-600" aria-hidden="true" />
          <div><h2 className="text-lg font-semibold">Evidencia de {active.cuenta}</h2><p className="text-sm text-slate-600">Semana desde el {dateLabel(active.fecha)}</p></div>
        </div>
        <dl className="grid grid-cols-2 gap-2.5">
          {Object.entries(activity).map(([key, name]) => <div key={key} className="min-w-0 rounded-xl bg-slate-50 p-2.5">
            <dt className="text-xs text-slate-600">{name}</dt>
            <dd className="mt-1 text-base font-semibold tabular-nums">{numberFormat.format(Number(active.variables[key]))}</dd>
          </div>)}
        </dl>
        {alerted(active) && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950">
          La puntuación supera el umbral de evaluación. Consulta las variables para interpretar el patrón.
        </p>}
      </section>}
    </div>
  </div>;
}

export function AttendancePractice({ data }: { data: Demo }) {
  const days = distinct(data.muestras.map((row) => row.fecha));
  const [day, setDay] = useState(days.at(-1) ?? "");
  const [filter, setFilter] = useState("");
  const [inspected, setInspected] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<number | null>(null);
  const level = (row: PracticeCase) => {
    if (data.umbrales.umbral_alto !== undefined && row.puntuacion >= data.umbrales.umbral_alto) return "Alto";
    if (data.umbrales.umbral_medio !== undefined && row.puntuacion >= data.umbrales.umbral_medio) return "Medio";
    return "Bajo";
  };
  const slots = data.muestras.filter((row) => row.fecha === day).sort((a, b) => b.puntuacion - a.puntuacion);
  const rows = slots.filter((row) => !filter || level(row) === filter);
  const active = rows.find((row) => row.id === inspected) ?? rows[0];
  const high = slots.filter((row) => level(row) === "Alto").length;
  const medium = slots.filter((row) => level(row) === "Medio").length;
  return <div className="space-y-4">
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Stat label="Turnos evaluados" value={slots.length} detail="Para la fecha seleccionada" />
      <Stat label="Riesgo alto" value={high} detail="Prioridad para seguimiento" />
      <Stat label="Riesgo medio" value={medium} detail="Seguimiento según criterio del administrador" />
    </dl>
    <Panel title="Distribución de riesgo" subtitle={day ? dateLabel(day) : undefined}>
      <Ring label="Turnos" data={[
        { label: "Bajo", value: slots.length - high - medium, color: "#16766e" },
        { label: "Medio", value: medium, color: "#3978b2" },
        { label: "Alto", value: high, color: "#bb6d20" },
      ]} />
    </Panel>
    <div className="grid items-start gap-4 xl:grid-cols-[1.5fr_1fr]">
      <section className={`${card} min-w-0 space-y-4`}>
        <h2 className="text-lg font-semibold">Turnos por prioridad</h2>
        <div className="flex flex-wrap items-end gap-3">
          <Days days={days} day={day} onChange={setDay} />
          <Select label="Nivel de riesgo" value={filter} onChange={(event) => setFilter(event.target.value)} options={[
            { value: "", label: "Todos los niveles" }, ...["Alto", "Medio", "Bajo"].map((value) => ({ value, label: value })),
          ]} />
        </div>
        <DataTable title="Turnos por prioridad" columns={["Turno", "Horario", "Riesgo", "Detalle"]}
          rows={rows.map((row) => ({ id: row.id, cells: [
            courtLabel(row), slotLabel(row),
            <Tag color={level(row) === "Alto" ? "amber" : level(row) === "Medio" ? "blue" : "green"}>{level(row)} · {percent(row.puntuacion)}</Tag>,
            <button type="button" onClick={() => { setInspected(row.id); setRevealed(null); }} aria-pressed={active?.id === row.id}
              className="inline-flex items-center gap-1.5 font-semibold text-[#175b91] hover:underline"
              aria-label={`Consultar ${courtLabel(row)} a las ${hourLabel(Number(row.variables.hora))}`}>
              Ver <FaArrowRight size={10} aria-hidden="true" />
            </button>,
          ] }))} />
      </section>
      {active && <section className={`${card} space-y-4`} aria-live="polite">
        <div className="flex items-start gap-3">
          <FaCalendarCheck className="mt-1.5 text-[#1B6EB6]" aria-hidden="true" />
          <div><h2 className="text-lg font-semibold">{courtLabel(active)} · {sport(active)}</h2><p className="text-sm text-slate-600">{dateLabel(active.fecha)} · {slotLabel(active)}</p></div>
        </div>
        <dl className="space-y-2 rounded-xl bg-slate-50 p-3 text-sm">
          <div className="flex justify-between gap-2"><dt>Cuenta</dt><dd className="font-semibold">{active.cuenta}</dd></div>
          <div className="flex justify-between gap-2"><dt>Modalidad</dt><dd className="font-semibold">{active.variables.tipo}</dd></div>
          <div className="flex justify-between gap-2"><dt>Antelación</dt><dd className="font-semibold">{Math.round(Math.expm1(Number(active.variables.anticipacion_log_horas)))} h</dd></div>
          <div className="flex justify-between gap-2"><dt>Probabilidad de inasistencia</dt><dd className="font-semibold">{percent(active.puntuacion)}</dd></div>
        </dl>
        {level(active) === "Alto" && <p className="flex items-start gap-2 text-sm text-slate-700">
          <FaSlidersH className="mt-1 shrink-0 text-[#1B6EB6]" aria-hidden="true" /> Confirma la reserva con la cuenta antes del turno.
        </p>}
        {revealed === active.id ? <p role="status" className="text-sm">Resultado del caso · <strong>{active.objetivo ? "Inasistencia" : "Asistió"}</strong></p> :
          <Button type="button" size="sm" variant="secondary" onClick={() => setRevealed(active.id)}>Mostrar resultado del turno</Button>}
      </section>}
    </div>
  </div>;
}
