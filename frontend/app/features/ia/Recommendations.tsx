import { Link, useFetcher } from "react-router";
import { Button } from "~/shared/components/ui";
import { label, percent } from "./shared";
import type { Demand } from "./types";

export function Recommendations({ date, kind, select }: {
  date: string;
  kind: "Normal" | "Especial";
  select: (court: number, time: string) => void;
}) {
  const fetcher = useFetcher<{ ok: true; result: Demand } | { ok: false; error: string; code?: string }>();
  const params = new URLSearchParams({ fecha: date, tipo: kind });
  return <section className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-sm font-bold text-slate-800">Horarios recomendados</h2>
      <Button type="button" size="sm" variant="secondary" loading={fetcher.state !== "idle"}
        onClick={() => void fetcher.load(`/api/horarios-recomendados?${params}`)}>
        Buscar alternativas para {date}
      </Button>
    </div>
    {fetcher.state === "idle" && fetcher.data?.ok === false && <p role="alert" className="text-sm text-red-700">
      {fetcher.data.error} {fetcher.data.code === "RESERVATION_RESTRICTED" &&
        <Link className="underline" to="/mi-situacion">Ver mi situación</Link>}
    </p>}
    {fetcher.state === "idle" && fetcher.data?.ok && <div className="space-y-2">
      <p role="status" className="text-sm text-slate-600">{fetcher.data.result.mensaje}</p>
      <div className="flex flex-wrap gap-2">
        {fetcher.data.result.turnos.map((slot) => {
          const time = `${slot.hora_inicio.slice(0, 5)} - ${slot.hora_fin.slice(0, 5)}`;
          return <Button key={`${slot.id_l}:${time}`} type="button" size="sm" variant="secondary"
            onClick={() => select(slot.id_l, time)}>
            {slot.losa} · {time}{slot.demanda !== null && ` · ${label(slot.fuente)} ${percent(slot.demanda)}`}
          </Button>;
        })}
      </div>
    </div>}
  </section>;
}

