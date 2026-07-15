import { NavLink } from "react-router-dom";
import { FileStack, Gauge, LogOut, PlayCircle, Radar } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";

const LINKS = [
  { to: "/", label: "Dashboard", end: true, icon: Gauge },
  { to: "/sources", label: "Fuentes", end: false, icon: Radar },
  { to: "/runs", label: "Runs", end: false, icon: PlayCircle },
  { to: "/documents", label: "Documentos", end: false, icon: FileStack },
];

export function Sidebar() {
  const { logout } = useAuth();

  return (
    <nav className="flex h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 pt-6 pb-5">
        <p className="font-display text-xl font-semibold tracking-tight">IURISYNC</p>
        <p className="mt-0.5 text-[0.6875rem] tracking-[0.18em] text-sidebar-foreground/50 uppercase">
          Sala de vigilancia
        </p>
      </div>

      <ul className="flex-1 space-y-1 px-3">
        {LINKS.map((link) => {
          const Icon = link.icon;
          return (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                  }`
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {link.label}
              </NavLink>
            </li>
          );
        })}
      </ul>

      <div className="border-t border-sidebar-border px-3 py-3">
        <button
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          <LogOut className="size-4 shrink-0" aria-hidden="true" />
          Cerrar sesión
        </button>
      </div>
    </nav>
  );
}
