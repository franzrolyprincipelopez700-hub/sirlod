import { Form, data, useActionData, useLoaderData, useNavigation } from "react-router";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { FaCheckCircle, FaRobot, FaShieldAlt, FaTimesCircle } from "react-icons/fa";
import { requireRole } from "~/services/auth.server";
import { api } from "~/services/api.server";
import { Badge, Button } from "~/shared/components/ui";

interface PendingPermission {
  id_p: number;
  fecha_creacion: string;
  tiene_documento: boolean;
  tipo: string;
  duracion_t: number;
  estado: string;
}

interface ReviewResult {
  id_p: number;
  decision: "Aceptado" | "Rechazado" | "Pendiente";
  motivo: string;
}

interface ReviewSummary {
  procesados: number;
  aceptados: number;
  rechazados: number;
  pendientes: number;
  resultados: ReviewResult[];
}

export async function loader({ request }: LoaderFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  const response = await api.get("/permisos?estado=Pendiente", request);
  const permissions = ((response as Record<string, unknown>).data || []) as PendingPermission[];
  return { pending: permissions.filter((item) => item.tipo === "Especial") };
}

export async function action({ request }: ActionFunctionArgs) {
  await requireRole(request, "trabajador", "Administrador");
  try {
    const form = await request.formData();
    const permissionId = form.get("id_permiso");
    if (permissionId !== null && (typeof permissionId !== "string" || !/^[1-9]\d*$/.test(permissionId))) {
      return data({ ok: false, error: "Identificador de permiso inválido." }, { status: 422 });
    }
    const query = permissionId ? `?id_permiso=${permissionId}` : "";
    const response = await api.post(`/permisos/revision-automatica${query}`, request, undefined, 60_000);
    return data({ ok: true, summary: (response as Record<string, unknown>).data as ReviewSummary });
  } catch (error) {
    return data(
      { ok: false, error: error instanceof Error ? error.message : "No se pudo ejecutar la revisión" },
      { status: 500 },
    );
  }
}

const rules = [
  "Solicitante activo en el padrón de estudiantes UNHEVAL",
  "PDF legible con nombre o código del estudiante",
  "Firma manuscrita o digital visible",
  "Aniversario de escuela profesional o facultad",
  "Campeonato o actividad organizada por estudiantes UNHEVAL",
  "Fecha y horario del documento coinciden con la solicitud",
  "Uno o más bloques horarios válidos",
  "Fecha vigente y no bloqueada",
  "Horario dentro de la apertura configurada",
  "Losa y disciplina activas",
  "Sin cruce con reservas aceptadas",
];

export default function AutomaticReviewPage() {
  const { pending } = useLoaderData<typeof loader>();
  const result = useActionData<typeof action>();
  const navigation = useNavigation();
  const reviewing = navigation.state !== "idle";
  const activePermission = navigation.formData?.get("id_permiso");
  const summary = result && "summary" in result ? result.summary : null;
  const error = result && "error" in result ? result.error : null;

  return (
    <div className="max-w-6xl space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-xl text-white shadow-md">
            <FaRobot aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-slate-800">Revisión automática de permisos especiales</h1>
            <p className="text-sm text-slate-500">Gemini lee el sustento. SIRLOD aplica las reglas de decisión y deriva los casos dudosos a revisión manual.</p>
          </div>
        </div>
        <Form method="post">
          <Button type="submit" loading={reviewing && !activePermission} disabled={reviewing || pending.length === 0}>
            <FaRobot aria-hidden="true" /> Revisar {pending.length} pendientes
          </Button>
        </Form>
      </header>

      <section className="card-theme p-6" aria-labelledby="review-rules-title">
        <div className="mb-4 flex items-center gap-2">
          <FaShieldAlt className="text-blue-600" aria-hidden="true" />
          <h2 id="review-rules-title" className="font-bold text-slate-800">Reglas aplicadas</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {rules.map((rule) => (
            <div key={rule} className="flex items-start gap-2 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3 text-sm text-slate-700">
              <FaCheckCircle className="mt-0.5 shrink-0 text-emerald-600" aria-hidden="true" />
              <span>{rule}</span>
            </div>
          ))}
        </div>
      </section>

      {pending.length > 0 && (
        <section className="card-theme p-6" aria-labelledby="pending-special-title">
          <h2 id="pending-special-title" className="mb-4 font-bold text-slate-800">Permisos especiales pendientes</h2>
          <ul className="divide-y divide-slate-100">
            {pending.map((item) => (
              <li key={item.id_p} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="font-semibold text-slate-800">Permiso #{item.id_p}</p>
                  <p className="text-sm text-slate-500">{item.tiene_documento ? "Con PDF de sustento" : "Sin PDF de sustento"}</p>
                </div>
                <Form method="post">
                  <input type="hidden" name="id_permiso" value={item.id_p} />
                  <Button type="submit" variant="secondary" disabled={reviewing}
                    loading={reviewing && activePermission === String(item.id_p)}>
                    Revisar permiso
                  </Button>
                </Form>
              </li>
            ))}
          </ul>
        </section>
      )}

      {result?.ok && summary && (
        <section className="card-theme p-6" aria-live="polite">
          <h2 className="mb-4 font-bold text-slate-800">Resultado de la revisión</h2>
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Revisados" value={summary.procesados} />
            <Metric label="Aceptados" value={summary.aceptados} tone="success" />
            <Metric label="Rechazados" value={summary.rechazados} tone="danger" />
            <Metric label="Siguen pendientes" value={summary.pendientes} tone="warning" />
          </div>
          <div className="space-y-3">
            {summary.resultados.map((item: ReviewResult) => (
              <article key={item.id_p} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-semibold text-slate-800">Permiso #{item.id_p}</p>
                  <p className="text-sm text-slate-500">{item.motivo}</p>
                </div>
                <Badge variant={item.decision === "Pendiente" ? "warning" : item.decision === "Aceptado" ? "success" : "danger"} dot>{item.decision}</Badge>
              </article>
            ))}
          </div>
        </section>
      )}

      {result && !result.ok && (
        <div role="alert" className="card-theme flex items-center gap-3 border-red-200 p-5 text-red-700">
          <FaTimesCircle aria-hidden="true" /> {error}
        </div>
      )}

      {pending.length === 0 && !result?.ok && (
        <div className="card-theme p-10 text-center text-slate-500">No hay permisos especiales pendientes por revisar.</div>
      )}
    </div>
  );
}

function Metric({ label, value, tone = "primary" }: { label: string; value: number; tone?: "primary" | "success" | "danger" | "warning" }) {
  const colors = { primary: "bg-blue-50 text-blue-700", success: "bg-emerald-50 text-emerald-700", danger: "bg-red-50 text-red-700", warning: "bg-amber-50 text-amber-800" };
  return <div className={`rounded-xl p-4 ${colors[tone]}`}><p className="text-xs font-semibold uppercase">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>;
}
