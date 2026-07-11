const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-200 text-gray-800",
  running: "bg-blue-200 text-blue-800",
  completed: "bg-green-200 text-green-800",
  failed: "bg-red-200 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? "bg-gray-200 text-gray-800";
  return <span className={`rounded-full px-2 py-1 text-xs font-medium ${className}`}>{status}</span>;
}
