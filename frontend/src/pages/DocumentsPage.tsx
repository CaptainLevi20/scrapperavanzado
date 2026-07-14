import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { buildDownloadFilename, downloadDocumentFile, fetchDocuments, updateDocumentReviewStatus } from "../api/documents";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchAllActiveSources } from "../api/sources";
import type { DocumentReviewStatus } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatBytes, formatDate } from "../lib/formatters";

const PAGE_SIZE = 50;

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [familyKey, setFamilyKey] = useState("");
  const [reviewStatus, setReviewStatus] = useState<DocumentReviewStatus | "">("");
  const [page, setPage] = useState(0);

  const queryClient = useQueryClient();

  const sourcesQuery = useQuery({
    queryKey: ["sources", "for-documents-filter"],
    queryFn: fetchAllActiveSources,
  });

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, familyKey, reviewStatus, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        family_key: familyKey || undefined,
        review_status: reviewStatus || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadMutation = useMutation({
    mutationFn: ({ id, filename }: { id: number; filename: string }) => downloadDocumentFile(id, filename),
    onError: () => setDownloadError("Error al descargar el documento"),
  });

  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
    onError: () => setReviewError("Error al marcar el documento"),
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
        <label className="flex items-center gap-2 text-sm">
          Revisión
          <select
            value={reviewStatus}
            onChange={(event) => {
              setReviewStatus(event.target.value as DocumentReviewStatus | "");
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todos</option>
            <option value="pending">Sin revisar</option>
            <option value="useful">Útil</option>
            <option value="not_useful">No útil</option>
          </select>
        </label>
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}
      {reviewError && <ErrorBanner message={reviewError} onRetry={() => setReviewError(null)} />}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Título</th>
            <th className="py-2">Tipo</th>
            <th className="py-2">Sección</th>
            <th className="py-2">Especialidad</th>
            <th className="py-2">Magistrado</th>
            <th className="py-2">Fecha providencia</th>
            <th className="py-2">Tamaño</th>
            <th className="py-2">Revisión</th>
            <th className="py-2">Descargar</th>
          </tr>
        </thead>
        <tbody>
          {documentsQuery.data?.items.map((document) => (
            <tr key={document.id} className="border-b">
              <td className="py-2" title={document.detalle ?? undefined}>
                {document.title}
                {document.source_url && (
                  <a
                    href={document.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 text-xs text-blue-600 underline"
                  >
                    Ver original ↗
                  </a>
                )}
              </td>
              <td className="py-2">{document.tipo ?? "—"}</td>
              <td className="py-2">{document.seccion ?? "—"}</td>
              <td className="py-2">{document.especialidad ?? "—"}</td>
              <td className="py-2">{document.magistrado ?? "—"}</td>
              <td className="py-2">{formatDate(document.f_providencia)}</td>
              <td className="py-2">{formatBytes(document.file_size_bytes)}</td>
              <td className="py-2">
                <div className="flex gap-1">
                  <button
                    onClick={() => reviewMutation.mutate({ id: document.id, status: "useful" })}
                    aria-label={`Marcar "${document.title}" como útil`}
                    aria-pressed={document.review_status === "useful"}
                    className={`rounded border px-2 py-1 text-xs ${
                      document.review_status === "useful" ? "bg-green-600 text-white" : ""
                    }`}
                  >
                    Útil
                  </button>
                  <button
                    onClick={() => reviewMutation.mutate({ id: document.id, status: "not_useful" })}
                    aria-label={`Marcar "${document.title}" como no útil`}
                    aria-pressed={document.review_status === "not_useful"}
                    className={`rounded border px-2 py-1 text-xs ${
                      document.review_status === "not_useful" ? "bg-red-600 text-white" : ""
                    }`}
                  >
                    No útil
                  </button>
                </div>
              </td>
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
