import * as React from "react";

import { cn } from "@/lib/utils";

// A neutral pulsing placeholder shown while real content loads.
//
// Rendered as an inline-block <span> (not a <div>) so it is valid inside
// paragraphs and table cells alike — the dashboard stat cards drop one straight
// into a <p>, where a block-level element would be invalid HTML.
//
// Uses bg-foreground/10 rather than bg-muted: in dark mode --muted and --card
// resolve to the same ink tone, which would make the skeleton invisible on a
// card. A translucent tint of the foreground contrasts in both themes.
//
// The pulse is disabled under prefers-reduced-motion, and the element is hidden
// from assistive tech (it carries no information — the surrounding container
// signals "loading" via aria-busy instead).
function Skeleton({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="skeleton"
      aria-hidden="true"
      className={cn(
        "inline-block animate-pulse rounded-md bg-foreground/10 align-middle motion-reduce:animate-none",
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
