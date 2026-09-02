import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  getCaliDecretosStatus,
  startCaliDecretos,
  stopCaliDecretos,
  type CaliDecretosEstado,
} from "../../api/caliDecretos";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

const EN_CURSO = "en_curso";

const ETIQUETA_ESTADO: Record<CaliDecretosEstado["estado"], string> = {
  en_curso: "En curso",
  detenido: "Detenido",
  terminado: "Terminado",
  terminado_con_fallos: "Terminado con fallos",
};

function etiquetaIniciar(estado: CaliDecretosEstado | null): string {
  if (!estado) return "Iniciar";
  if (estado.estado === "terminado_con_fallos") return "Reintentar fallidos";
  if (estado.estado === "detenido") return "Reanudar";
  if (estado.estado === "terminado") return "Revisar de nuevo";
  return "Iniciar";
}

function num(n: number): string {
  return n.toLocaleString("es-CO");
}

function Metrica({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{etiqueta}</dt>
      <dd className="font-mono-num">{num(valor)}</dd>
    </div>
  );
}

function ListaCopiable({ lineas }: { lineas: string[] }) {
  return (
    <div className="mt-2 space-y-1">
      <Button
        variant="outline"
        size="xs"
        onClick={() => void navigator.clipboard?.writeText(lineas.join("\n"))}
      >
        Copiar lista
      </Button>
      <pre className="max-h-64 overflow-auto rounded bg-secondary/40 p-2 text-[0.7rem] leading-tight">
        {lineas.join("\n")}
      </pre>
    </div>
  );
}

export function CaliDecretosPanel() {
  const [path, setPath] = useState("");
  const [estado, setEstado] = useState<CaliDecretosEstado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pathRef = useRef(path);
  pathRef.current = path;

  const refrescar = useCallback(async (p: string) => {
    if (!p) return;
    try {
      setEstado(await getCaliDecretosStatus(p));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setEstado(null);
    }
  }, []);

  useEffect(() => {
    if (estado?.estado !== EN_CURSO) return;
    const id = setInterval(() => void refrescar(pathRef.current), 3000);
    return () => clearInterval(id);
  }, [estado?.estado, refrescar]);

  async function accion(fn: () => Promise<CaliDecretosEstado>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      setEstado(await fn());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const enCurso = estado?.estado === EN_CURSO;
  const progreso =
    estado && estado.total_paginas
      ? Math.round((estado.ultima_pagina_completada / estado.total_paginas) * 100)
      : 0;
  const fallidosFtp = estado?.fallidos.filter((f) => f.motivo === "ftp-no-disponible").length ?? 0;
  const fallidosOtros = (estado?.fallidos.length ?? 0) - fallidosFtp;
  const listaRecortada = estado ? estado.fallidos.length < estado.fallidos_count : false;
  const avisosRecortada = estado ? estado.avisos.length < estado.avisos_count : false;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Descarga todos los decretos publicados en{" "}
        <code>cali.gov.co/&hellip;/consulta-de-decretos</code> a la carpeta indicada, organizados como{" "}
        <code>DECRETOS/ALCACALI/&#123;año&#125;/D_ALCACALI_&#123;número&#125;_&#123;año&#125;.pdf</code>.
        Son ~72.000 archivos: puede ocupar decenas o cientos de GB y tardar varias horas. Podés cerrar
        esta pestaña mientras corre; la descarga sigue en el servidor.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span>Carpeta de destino</span>
          <Input
            value={path}
            onChange={(ev) => setPath(ev.target.value)}
            onBlur={() => void refrescar(path)}
            placeholder="D:\DESCARGA CALI"
          />
        </label>
        <Button
          onClick={() => void accion(() => startCaliDecretos(path), "No se pudo iniciar la descarga.")}
          disabled={!path || busy || enCurso}
        >
          {etiquetaIniciar(estado)}
        </Button>
        {enCurso && (
          <Button
            variant="secondary"
            onClick={() => void accion(() => stopCaliDecretos(path), "No se pudo detener la descarga.")}
            disabled={busy}
          >
            Detener
          </Button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {estado && (
        <div className="space-y-3 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{ETIQUETA_ESTADO[estado.estado]}</span>
            <span className="text-muted-foreground">
              Página {num(estado.ultima_pagina_completada)} de {num(estado.total_paginas ?? 0)}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded bg-secondary">
            <div className="h-full bg-primary transition-all" style={{ width: `${progreso}%` }} />
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <Metrica etiqueta="Descargados" valor={estado.descargados} />
            <Metrica etiqueta="Ya estaban" valor={estado.ya_existian} />
            <Metrica etiqueta="Duplicados" valor={estado.duplicados} />
            <Metrica etiqueta="Fallidos" valor={estado.fallidos_count} />
          </dl>
          {estado.fallidos_count > 0 && (
            <p className="text-xs text-muted-foreground">
              {num(fallidosFtp)} por FTP no disponible &middot; {num(fallidosOtros)} por otros errores
              {listaRecortada && " (lista recortada a 1.000)"}
            </p>
          )}
          {estado.fallidos.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer">Fallidos ({num(estado.fallidos.length)})</summary>
              <ListaCopiable
                lineas={estado.fallidos.map(
                  (f) => `${f.numero ?? "?"}\t${f.anio ?? "?"}\t${f.motivo}\t${f.url}`,
                )}
              />
            </details>
          )}
          {estado.avisos.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer">
                Avisos ({num(estado.avisos_count)}){avisosRecortada && " (lista recortada a 1.000)"}
              </summary>
              <ListaCopiable
                lineas={estado.avisos.map(
                  (a) =>
                    `${a.tipo}\t${a.numero ?? ""}\t${a.anio ?? ""}\t${a.guardado_como ?? a.url ?? ""}`,
                )}
              />
            </details>
          )}
        </div>
      )}
    </div>
  );
}
