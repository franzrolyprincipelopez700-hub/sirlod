import type { ReactNode } from "react";
import { FaChartBar } from "react-icons/fa";
import { card } from "./shared";
import type { Indicator } from "./types";

type Point = { label: string; value: number; color?: string };
const colors = ["#0b7872", "#3986c4", "#bc6e20", "#8f4361", "#687b91"];
export const integer = new Intl.NumberFormat("es-PE");
export const decimal = new Intl.NumberFormat("es-PE", { maximumFractionDigits: 3 });
const dates = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short", timeZone: "UTC" });
export const dayLabel = (day: string) => dates.format(new Date(day + "T12:00:00Z"));

export function total(values: Indicator[]) {
  return values.reduce((sum, item) => sum + item.valor, 0);
}

export function Panel({ title, subtitle, children, className = "" }: {
  title: string; subtitle?: string; children: ReactNode; className?: string;
}) {
  return <section className={card + " ml-panel min-w-0 space-y-4 " + className}>
    <div>
      <h2 className="text-lg font-bold text-slate-900">{title}</h2>
      {subtitle && <p className="mt-1 text-sm leading-relaxed text-slate-600">{subtitle}</p>}
    </div>
    {children}
  </section>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="ml-empty">
    <FaChartBar aria-hidden="true" />
    <p>{children}</p>
  </div>;
}

export function HorizontalBars({ data, label, format = (value) => integer.format(value) }: {
  data: Point[]; label: string; format?: (value: number) => string;
}) {
  if (!data.some(({ value }) => value > 0)) return <Empty>Sin registros para este periodo.</Empty>;
  const max = Math.max(...data.map(({ value }) => value));
  return <ul className="ml-hbars" aria-label={label}>
    {data.map(({ label: key, value, color }, index) => <li key={key}>
      <span>{key}</span>
      <div className="ml-hbar-track" aria-hidden="true">
        <div style={{ width: value / max * 100 + "%", backgroundColor: color ?? colors[index % colors.length] }} />
      </div>
      <strong>{format(value)}</strong>
    </li>)}
  </ul>;
}

export function HourBars({ data }: { data: Indicator[] }) {
  if (data.length === 0) return <Empty>Este periodo aún no tiene turnos aprobados.</Empty>;
  const max = Math.max(1, ...data.map((item) => item.valor));
  return <div className="overflow-x-auto">
    <ul className="ml-hour-chart" aria-label="Turnos aprobados por hora">
      {data.map(({ clave, valor }) => <li key={clave}>
        <strong>{integer.format(valor)}</strong>
        <div className="ml-hour-column"><span style={{ height: valor / max * 100 + "%" }} /></div>
        <span>{clave}</span>
      </li>)}
    </ul>
  </div>;
}

export function Ring({ data, label }: { data: Point[]; label: string }) {
  const sum = data.reduce((value, row) => value + row.value, 0);
  if (!sum) return <Empty>No hay resultados registrados en el periodo.</Empty>;
  let position = 0;
  const segments = data.flatMap(({ value, color }, index) => {
    if (!value) return [];
    const begin = position;
    position += value / sum * 100;
    return [(color ?? colors[index % colors.length]) + " " + begin + "% " + position + "%"];
  });
  return <div className="ml-ring-layout">
    <div className="ml-ring" style={{ background: "conic-gradient(" + segments.join(",") + ")" }} aria-hidden="true">
      <div><strong>{integer.format(sum)}</strong><span>{label}</span></div>
    </div>
    <ul className="ml-legend" aria-label={label}>
      {data.map(({ label: key, value, color }, index) => <li key={key}>
        <span className="ml-dot" style={{ backgroundColor: color ?? colors[index % colors.length] }} />
        <span>{key}</span><strong>{integer.format(value)}</strong>
      </li>)}
    </ul>
  </div>;
}
