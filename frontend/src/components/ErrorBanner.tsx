export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border-[1.5px] border-rojo/40 bg-rojo-bg px-4 py-2.5 text-rojo">
      <span className="text-sm font-medium">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 text-sm font-semibold underline underline-offset-2 hover:text-rojo/80">
          Reintentar
        </button>
      )}
    </div>
  );
}
