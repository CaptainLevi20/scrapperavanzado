import { describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDebouncedValue } from "./useDebouncedValue";

describe("useDebouncedValue", () => {
  it("returns the initial value immediately", () => {
    const { result } = renderHook(() => useDebouncedValue("a", 300));
    expect(result.current).toBe("a");
  });

  it("only settles on the latest value after the delay elapses with no further changes", () => {
    vi.useFakeTimers();
    try {
      const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
        initialProps: { v: "a" },
      });

      // A burst of changes (like fast typing) keeps resetting the timer.
      rerender({ v: "ab" });
      rerender({ v: "abc" });
      expect(result.current).toBe("a");

      act(() => vi.advanceTimersByTime(299));
      expect(result.current).toBe("a"); // still within the window

      act(() => vi.advanceTimersByTime(1));
      expect(result.current).toBe("abc"); // settles on the final value, skipping "ab"
    } finally {
      vi.useRealTimers();
    }
  });
});
