import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Masthead } from "./Masthead";

export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex h-screen flex-1 flex-col overflow-hidden">
        <Masthead />
        <main className="flex-1 overflow-y-auto bg-background p-8">
          <div className="mx-auto max-w-[90rem]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
