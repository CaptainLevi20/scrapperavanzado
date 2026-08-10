import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Masthead } from "./Masthead";
import { RouteFallback } from "../RouteFallback";

export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex h-screen flex-1 flex-col overflow-hidden">
        <Masthead />
        <main className="flex-1 overflow-y-auto bg-background p-8">
          <div className="mx-auto h-full max-w-[90rem]">
            {/* Boundary for lazily-loaded pages — kept here (not around the whole
                app) so the sidebar and masthead stay on screen while the next
                page's chunk loads; only the content area shows the fallback. */}
            <Suspense fallback={<RouteFallback />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}
