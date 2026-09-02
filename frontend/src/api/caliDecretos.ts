import { apiFetch, buildQuery } from "./client";

export interface CaliDecretosAviso {
  tipo: string;
  numero?: string | null;
  anio?: number | null;
  url?: string | null;
  guardado_como?: string | null;
}

export interface CaliDecretosFallido {
  numero?: string | null;
  anio?: number | null;
  url: string;
  motivo: string;
  intentos: number;
}

export type CaliDecretosEstadoNombre =
  | "en_curso"
  | "detenido"
  | "terminado"
  | "terminado_con_fallos";

export interface CaliDecretosEstado {
  version: number;
  estado: CaliDecretosEstadoNombre;
  iniciado: string;
  actualizado: string;
  terminado: string | null;
  total_registros_sitio: number | null;
  total_paginas: number | null;
  ultima_pagina_completada: number;
  descargados: number;
  ya_existian: number;
  duplicados: number;
  fallidos_count: number;
  avisos_count: number;
  detener_solicitado: boolean;
  concurrencia_actual: number;
  avisos: CaliDecretosAviso[];
  fallidos: CaliDecretosFallido[];
}

export function startCaliDecretos(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>("/cali-decretos/start", {
    method: "POST",
    body: JSON.stringify({ dest_path: destPath }),
  });
}

export function getCaliDecretosStatus(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>(`/cali-decretos/status${buildQuery({ dest_path: destPath })}`);
}

export function stopCaliDecretos(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>("/cali-decretos/stop", {
    method: "POST",
    body: JSON.stringify({ dest_path: destPath }),
  });
}
