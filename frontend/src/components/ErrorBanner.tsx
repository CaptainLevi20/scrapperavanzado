// "error" (red) is for actual failures — a request that broke and can be
// retried. "info" (the same gold used for the "en curso" status badge) is for
// messages that aren't reporting anything wrong, just informing the user of
// some state (e.g. "we paused auto-refresh") — using the error styling there
// reads as an alarm when nothing has actually failed.
const VARIANT_STYLES = {
  error: "border-rojo/40 bg-rojo-bg text-rojo",
  info: "border-sello/40 bg-sello/10 text-sello-ink",
} as const;

const VARIANT_BUTTON_STYLES = {
  error: "hover:text-rojo/80",
  info: "hover:text-sello-ink/80",
} as const;

export function ErrorBanner({
  message,
  onRetry,
  retryLabel = "Reintentar",
  variant = "error",
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  variant?: keyof typeof VARIANT_STYLES;
}) {
  return (
    <div className={`flex items-center justify-between gap-4 rounded-lg border-[1.5px] px-4 py-2.5 ${VARIANT_STYLES[variant]}`}>
      <span className="text-sm font-medium">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className={`shrink-0 text-sm font-semibold underline underline-offset-2 ${VARIANT_BUTTON_STYLES[variant]}`}
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
