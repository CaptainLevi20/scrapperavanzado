import { useEffect, useState } from "react";

// Returns a copy of `value` that only updates after it has stopped changing for
// `delayMs`. Used to debounce the documents search box: the <input> stays bound
// to the immediate value (so typing feels instant), while the query key reads
// this debounced copy — so a burst of keystrokes triggers a single request once
// the user pauses, instead of one request per character.
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
