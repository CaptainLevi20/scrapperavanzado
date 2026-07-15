import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// A styled wrapper around a plain <select> — NOT a Radix/Combobox replacement.
// Keeping the real <select>/<option> DOM means existing interactions
// (userEvent.selectOptions, getByLabelText) keep working unchanged; this only
// adds a consistent look (custom chevron, focus ring, sizing) on top of it.
function NativeSelect({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative inline-block">
      <select
        data-slot="native-select"
        className={cn(
          "h-9 w-full appearance-none rounded-md border-[1.5px] border-input bg-card py-1 pr-8 pl-3 text-sm text-foreground shadow-xs outline-none transition-colors",
          "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
          "disabled:pointer-events-none disabled:opacity-50",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}

export { NativeSelect };
