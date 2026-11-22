export interface DemandSlot {
  id_l: number;
  losa: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  disponible: boolean;
  demanda: number | null;
  fuente: "modelo_real" | "frecuencia_historica" | "disponibilidad";
}

export interface Demand {
  mensaje: string;
  turnos: DemandSlot[];
}

export interface AttendanceSlot {
  detalle_id: number;
  permiso_id: number;
  usuario_id: number | null;
  codigo: string | null;
  losa: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  resultado: string;
  asistencia_id: number | null;
  evidencia: string | null;
  actor_id: number | null;
  registrado: string | null;
  registrable: boolean;
  predecible: boolean;
}

export interface Risk {
  disponible: boolean;
  riesgo?: number;
  nivel?: string;
  mensaje: string;
}

export interface Measure {
  id: number;
  incidente_id: number;
  norma_id: number;
  tipo: string;
  estado: string;
  inicio: string;
  fin: string | null;
  motivo: string;
}

export interface Appeal {
  id: number;
  medida_id: number;
  texto: string;
  creado: string;
  decision: string | null;
  revisor_id: number | null;
  revisado: string | null;
}

export interface Case {
  id: number;
  usuario_id: number;
  codigo?: string;
  tipo: string;
  estado: string;
  ocurrido: string;
  gravedad: string | null;
  asistencia_id: number | null;
  evidencia: Record<string, unknown>;
}

export interface Decision {
  id: number;
  incidente_id: number;
  actor_id: number;
  accion: string;
  motivo: string;
  creado: string;
  datos: Record<string, unknown>;
}

export interface History {
  infracciones_validas: number;
  incidentes: Case[];
  medidas: Measure[];
  descargos: Appeal[];
  decisiones: Decision[];
}

export interface Policy {
  id: number;
  tipo: string;
  gravedad: string;
  medida: string;
  minimo_previas: number;
  maximo_horas: number | null;
  fundamento: string;
  criterio: string;
  aprobacion: string | null;
  aprobada: string | null;
  vigente: boolean;
}

export type Module = "demanda" | "anomalias" | "inasistencia";

export interface Version {
  version: string;
  modo: "demo" | "real";
  estado: string;
  algoritmo: string | null;
  activo: boolean;
  creado: string;
  evaluacion: {
    total: number;
    motivo?: string;
    prueba?: Record<string, number | unknown>;
    [key: string]: unknown;
  };
}

export interface ModelGroup {
  modulo: Module;
  activo: Version | null;
  versiones: Version[];
  compatible: boolean | null;
  predicciones_registradas: number;
}

export interface PracticeCase {
  id: number;
  fecha: string;
  cuenta: string | null;
  variables: Record<string, string | number>;
  objetivo: number;
  puntuacion: number;
}

export interface Demo {
  modo: "demo";
  version: string;
  umbrales: { umbral?: number; umbral_medio?: number; umbral_alto?: number };
  muestras: PracticeCase[];
}

export type WorkspaceView = "practica" | "operacion";

