import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Resumen", end: true },
  { to: "/sources", label: "Fuentes", end: false },
  { to: "/runs", label: "Runs", end: false },
  { to: "/documents", label: "Documentos", end: false },
];

export function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r p-4">
      <p className="mb-6 text-lg font-bold">IURISYNC</p>
      <ul className="space-y-2">
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `block rounded px-3 py-2 ${isActive ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
