import { useState } from "react";
import { Form, useLoaderData, type LoaderFunctionArgs } from "react-router";
import { FaArrowRight, FaCalendarCheck } from "react-icons/fa";
import { requireRole } from "~/services/auth.server";
import { Button, Input, Select } from "~/shared/components/ui";
import { dayLabel, Empty, HorizontalBars, HourBars, integer, Panel, total } from "./charts";
import { failure, loadWorkspace, reply } from "./learning.server";
import { DataTable, DemandPractice, Tag } from "./practice";
import { campusDate, label, percent } from "./shared";
import type { DashboardSummary, Demand, DemandSlot } from "./types";
import { ModelDetails, Stat, Workspace, WorkspaceError } from "./workspace";

export { action } from "./panel.server";

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  try {
    return reply(request, { ok: true as const, ...await loadWorkspace(request, "demanda") });
  } catch (error) {
    return failure(request, error);
  }
}

const dateValue = (day: string, offset: number) =>
  new Date(Date.parse(day + "T12:00:00Z") + offset * 86400000).toISOString().slice(0, 10);

const interval = (slot: DemandSlot) => slot.hora_inicio.slice(0, 5) + "–" + slot.hora_fin.slice(0, 5);

function Availability({ forecast, date }: { forecast: Demand; date: string }) {
  const courts = [...new Map(forecast.turnos.map((slot) => [slot.id_l, slot.losa])).entries()];
  const hours = [...new Set(forecast.turnos.map((slot) => slot.hora_inicio))].sort();
  const [court, setCourt] = useState("");
  const selected = forecast.turnos.filter((slot) => !court || String(slot.id_l) === court);
  const bySlot = new Map(selected.map((slot) => [slot.id_l + ":" + slot.hora_inicio, slot]));
  const options = selected.filter((slot) => slot.disponible).sort((a, b) =>
    (a.demanda ?? Infinity) - (b.demanda ?? Infinity) || a.hora_inicio.localeCompare(b.hora_inicio)).slice(0, 3);

  return <div className="space-y-4">
    <Panel title="Mapa de disponibilidad" subtitle={dayLabel(date) + " · Hora de Lima"}>
      {selected.length ? <>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Select className="!mb-0 min-w-48" label="Losa" value={court}
            onChange={(event) => setCourt(event.target.value)}
            options={[{ value: "", label: "Todas las losas" }, ...courts.map(([id, name]) => ({ value: String(id), label: name }))]} />
          <div className="flex items-center gap-2 text-xs font-semibold"><span className="ml-free rounded px-2 py-1">Libre</span><span className="ml-busy rounded px-2 py-1">Ocupada</span></div>
        </div>
        <div className="overflow-x-auto" role="region" aria-label="Mapa de disponibilidad por hora" tabIndex={0}>
          <table className="ml-heatmap w-full">
            <caption className="sr-only">Estado actual de los turnos de cada losa</caption>
            <thead><tr><th scope="col">Losa</th>{hours.map((hour) => <th key={hour} scope="col">{hour.slice(0, 5)}</th>)}</tr></thead>
            <tbody>{courts.filter(([id]) => !court || String(id) === court).map(([id, name]) => <tr key={id}>
              <th scope="row">{name}</th>
              {hours.map((hour) => {
                const slot = bySlot.get(id + ":" + hour);
                const status = slot ? slot.disponible ? "Libre" : "Ocupada" : "Sin turno";
                return <td key={hour} title={status} className={slot ? slot.disponible ? "ml-free" : "ml-busy" : "ml-missing"}>
                  <span aria-hidden="true">{slot ? slot.disponible ? "✓" : "×" : "—"}</span>
                  <span className="sr-only">{status}</span>
                </td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
        <p className="text-xs text-slate-600">{forecast.mensaje} La reserva se valida al solicitarla.</p>
      </> : <Empty>{forecast.mensaje}</Empty>}
    </Panel>
    {options.length > 0 && <Panel title="Alternativas libres" subtitle="Ordenadas por demanda disponible y hora de inicio.">
      <ul className="grid gap-2 xl:grid-cols-3">{options.map((slot) =>
        <li key={slot.id_l + ":" + slot.hora_inicio} className="flex items-start gap-3 rounded-xl bg-emerald-50 p-3">
          <FaArrowRight className="mt-1 shrink-0 text-emerald-700" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-emerald-950">{slot.losa}</p>
            <p className="text-sm text-emerald-800">{interval(slot)}</p>
            <p className="mt-1 text-xs text-emerald-900">{slot.demanda !== null
              ? percent(slot.demanda) + " · " + label(slot.fuente)
              : "Disponibilidad registrada"}</p>
          </div>
        </li>)}</ul>
    </Panel>}
    {selected.length > 0 && <details className="ml-panel rounded-2xl border bg-white p-4">
      <summary className="cursor-pointer font-semibold">Consultar turnos por losa y hora</summary>
      <div className="mt-3"><DataTable title="Detalle de los turnos" columns={["Losa", "Horario", "Estado", "Ocupación"]}
        rows={selected.map((slot) => ({
          id: slot.id_l + ":" + slot.hora_inicio,
          cells: [
            slot.losa, interval(slot), slot.disponible ? <Tag color="green">Libre</Tag> : <Tag>Ocupado</Tag>,
            slot.demanda === null ? "Sin estimación" : percent(slot.demanda) + " · " + label(slot.fuente),
          ],
        }))} /></div>
    </details>}
  </div>;
}

function DemandOperation({ summary }: { summary: DashboardSummary }) {
  const today = campusDate.format(new Date());
  const hours = summary.por_hora ?? [];
  const courts = summary.por_losa ?? [];
  const peak = hours.reduce<{ clave: string; valor: number } | null>((best, item) =>
    !best || item.valor > best.valor ? item : best, null);
  const date = summary.fecha_consulta ?? today;
  const available = summary.consulta?.turnos.filter((slot) => slot.disponible).length ?? 0;

  return <>
    <dl className="grid gap-3 sm:grid-cols-3">
      <Stat label="Turnos aprobados" value={integer.format(total(hours))} detail="Ocupación observada en los últimos 28 días" />
      <Stat label="Hora de mayor uso" value={peak?.clave ?? "—"} detail={peak ? peak.valor + " turnos aprobados en esa franja" : "Por determinar con registros"} />
      <Stat label="Turnos libres" value={summary.consulta ? available : "—"} detail={"En la consulta del " + dayLabel(date)} />
    </dl>
    <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
      <Panel title="Cuándo se usan las losas" subtitle={dayLabel(summary.inicio) + " al " + dayLabel(summary.fin)}>
        <HourBars data={hours} />
      </Panel>
      <Panel title="Losas más utilizadas" subtitle="Turnos aprobados por instalación">
        <HorizontalBars label="Reservas por losa" data={courts.map(({ clave, valor }) => ({ label: clave, value: valor }))} />
      </Panel>
    </div>
    <Form method="get" className="ml-panel flex flex-wrap items-end gap-3 rounded-2xl border bg-white p-4">
      <Input className="!mb-0" name="fecha" label="Fecha de consulta" type="date" min={today} max={dateValue(today, 30)}
        defaultValue={date} key={date} required />
      <Button type="submit" size="sm"><FaCalendarCheck aria-hidden="true" /> Consultar disponibilidad</Button>
    </Form>
    {summary.consulta && <Availability key={date} forecast={summary.consulta} date={date} />}
    {summary.error_consulta && <Empty>{summary.error_consulta}</Empty>}
  </>;
}

export default function DemandWorkspace() {
  const data = useLoaderData<typeof loader>();
  return <Workspace module="demanda" view={data.ok ? data.view : undefined}>
    {!data.ok ? <WorkspaceError message={data.error} /> : <>
      {data.view === "practica" ? data.practice
        ? <DemandPractice key={data.practice.version} data={data.practice} />
        : <WorkspaceError message={data.practiceError ?? "La evaluación no está disponible."} />
        : data.dashboard && <DemandOperation summary={data.dashboard} />}
      <ModelDetails model={data.model} view={data.view} />
    </>}
  </Workspace>;
}
