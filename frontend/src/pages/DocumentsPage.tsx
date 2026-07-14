import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { buildDownloadFilename, downloadDocumentFile, fetchDocuments } from "../api/documents";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchAllActiveSources } from "../api/sources";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatBytes, formatDate } from "../lib/formatters";

const PAGE_SIZE = 50;

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [familyKey, setFamilyKey] = useState("");
  const [page, setPage] = useState(0);

  const sourcesQuery = useQuery({
    queryKey: ["sources", "for-documents-filter"],
    queryFn: fetchAllActiveSources,
  });

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, familyKey, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        family_key: familyKey || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadMutation = useMutation({
    mutationFn: ({ id, filename }: { id: number; filename: string }) => downloadDocumentFile(id, filename),
    onError: () => setDownloadError("Error al descargar el documento"),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Documentos</h1>

      <div className="flex gap-3">
        <input
          placeholder="Buscar por título"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
        <input
          placeholder="Tipo"
          value={tipo}
          onChange={(event) => {
            setTipo(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
        <label className="flex items-center gap-2 text-sm">
          Fuente
          <select
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {sourcesQuery.data?.map((source) => (
              <option key={source.id} value={String(source.id)}>
                {source.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Familia
          <select
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Título</th>
            <th className="py-2">Tipo</th>
            <th className="py-2">Sección</th>
            <th className="py-2">Fecha providencia</th>
            <th className="py-2">Tamaño</th>
            <th className="py-2">Descargar</th>
          </tr>
        </thead>
        <tbody>
          {documentsQuery.data?.items.map((document) => (
            <tr key={document.id} className="border-b">
              <td className="py-2">{document.title}</td>
              <td className="py-2">{document.tipo ?? "—"}</td>
              <td className="py-2">{document.seccion ?? "—"}</td>
              <td className="py-2">{formatDate(document.f_providencia)}</td>
              <td className="py-2">{formatBytes(document.file_size_bytes)}</td>
              <td className="py-2">
                <button
                  onClick={() => downloadMutation.mutate({ id: document.id, filename: buildDownloadFilename(document) })}
                  className="text-sm text-blue-600 underline"
                >
                  Descargar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">Total: {documentsQuery.data?.total ?? 0}</p>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => setPage((current) => current + 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
