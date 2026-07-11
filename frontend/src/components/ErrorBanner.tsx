export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between rounded border border-red-300 bg-red-50 px-4 py-2 text-red-800">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-sm font-medium underline">
          Reintentar
        </button>
      )}
    </div>
  );
}
