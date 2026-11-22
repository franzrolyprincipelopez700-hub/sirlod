import { useLoaderData, type LoaderFunctionArgs } from "react-router";
import { requireRole } from "~/services/auth.server";
import { Input } from "~/shared/components/ui";
import { failure, loadWorkspace, reply } from "./learning.server";
import { DataTable, DemandPractice, Tag } from "./practice";
import { campusDate, card, label, Operation, percent } from "./shared";
import type { Demand } from "./types";
import { ModelDetails, Workspace, WorkspaceError } from "./workspace";

export { action } from "./panel.server";

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  try {
    return reply(request, { ok: true as const, ...await loadWorkspace(request, "demanda") });
  } catch (error) {
    return failure(request, error);
  }
}

function Forecast({ result }: { result: Demand }) {
  return <div className="space-y-3 pt-2">
    <p role="status" className="text-sm text-slate-600">{result.mensaje}</p>
    <DataTable title="Disponibilidad por turno" columns={["Losa", "Horario", "Disponibilidad", "Demanda"]}
      rows={result.turnos.map((slot) => ({
        id: `${slot.id_l}:${slot.hora_inicio}`,
        cells: [
          slot.losa, `${slot.hora_inicio.slice(0, 5)}–${slot.hora_fin.slice(0, 5)}`,
          slot.disponible ? <Tag color="green">Libre</Tag> : <Tag>Ocupado</Tag>,
          slot.demanda === null ? "Sin estimación" : `${percent(slot.demanda)} · ${label(slot.fuente)}`,
        ],
      }))} />
  </div>;
}

export default function DemandWorkspace() {
  const data = useLoaderData<typeof loader>();
  const today = campusDate.format(new Date());
  return <Workspace module="demanda" view={data.ok ? data.view : undefined}>
    {!data.ok ? <WorkspaceError message={data.error} /> : <>
      {data.view === "practica" ? data.practice
        ? <DemandPractice key={data.practice.version} data={data.practice} />
        : <WorkspaceError message={data.practiceError ?? "La práctica no está disponible."} /> :
        <section className={`${card} space-y-3`}>
          <h2 className="text-lg font-semibold">Disponibilidad por fecha</h2>
          <Operation<Demand> intent="demanda" label="Consultar turnos" view={(result) => <Forecast result={result} />}>
            <div className="max-w-xs"><Input type="date" name="fecha" label="Fecha" min={today} defaultValue={today} required /></div>
          </Operation>
        </section>}
      <ModelDetails model={data.model} view={data.view} />
    </>}
  </Workspace>;
}
