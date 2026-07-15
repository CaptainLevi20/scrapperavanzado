export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-10 text-center">
      <p className="font-display text-lg text-muted-foreground">{message}</p>
    </div>
  );
}
