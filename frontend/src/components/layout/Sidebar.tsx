import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Archive, FileStack, Gauge, LogOut, PanelLeftClose, PanelLeftOpen, PlayCircle, Radar } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { ChangePasswordDialog } from "./ChangePasswordDialog";

const LINKS = [
  { to: "/", label: "Dashboard", end: true, icon: Gauge },
  { to: "/sources", label: "Fuentes", end: false, icon: Radar },
  { to: "/runs", label: "Runs", end: false, icon: PlayCircle },
  { to: "/documents", label: "Documentos", end: false, icon: FileStack },
  { to: "/bulk-downloads", label: "Descargas masivas", end: false, icon: Archive },
];

// Persisted so the chosen width survives a reload — re-collapsing on every
// navigation would defeat the point of the toggle.
const COLLAPSE_STORAGE_KEY = "iurisync:sidebar-collapsed";

export function Sidebar() {
  const { username, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "true");

  useEffect(() => {
    localStorage.setItem(COLLAPSE_STORAGE_KEY, String(collapsed));
  }, [collapsed]);

  return (
    <nav
      className={`flex h-screen shrink-0 flex-col bg-sidebar text-sidebar-foreground transition-[width] duration-200 ${
        collapsed ? "w-16" : "w-60"
      }`}
    >
      <div className={`flex items-center pt-6 pb-5 ${collapsed ? "justify-center px-3" : "justify-between px-5"}`}>
        {!collapsed && (
          <div>
            <p className="font-display text-xl font-semibold tracking-tight">IURISYNC</p>
            <p className="mt-0.5 text-[0.6875rem] tracking-[0.18em] text-sidebar-foreground/50 uppercase">
              Sala de vigilancia
            </p>
          </div>
        )}
        <button
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expandir panel de navegación" : "Colapsar panel de navegación"}
          title={collapsed ? "Expandir" : "Colapsar"}
          className="shrink-0 rounded-md p-1.5 text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="size-4" aria-hidden="true" />
          )}
        </button>
      </div>

      <ul className="flex-1 space-y-1 px-3">
        {LINKS.map((link) => {
          const Icon = link.icon;
          return (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                title={collapsed ? link.label : undefined}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    collapsed ? "justify-center" : ""
                  } ${
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                  }`
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {!collapsed && link.label}
              </NavLink>
            </li>
          );
        })}
      </ul>

      <div className="space-y-1 border-t border-sidebar-border px-3 py-3">
        {username && !collapsed && (
          <p className="truncate px-3 pb-1 text-xs text-sidebar-foreground/50" title={username}>
            {username}
          </p>
        )}
        <ChangePasswordDialog collapsed={collapsed} />
        <button
          onClick={() => logout()}
          title={collapsed ? "Cerrar sesión" : undefined}
          className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <LogOut className="size-4 shrink-0" aria-hidden="true" />
          {!collapsed && "Cerrar sesión"}
        </button>
      </div>
    </nav>
  );
}
