import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListTree, Search, Cpu, Skull, LogOut } from "lucide-react";
import Pulse from "./Pulse";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/queues", label: "Queues", icon: ListTree },
  { to: "/jobs", label: "Job Explorer", icon: Search },
  { to: "/workers", label: "Workers", icon: Cpu },
  { to: "/dead-letter", label: "Dead Letter", icon: Skull },
];

export default function Sidebar() {
  const { user, project, logout } = useAuth();

  return (
    <aside className="flex h-full w-60 flex-col border-r border-hairline bg-surface">
      <div className="flex items-center gap-2 border-b border-hairline px-5 py-5">
        <Pulse className="h-5 w-9 shrink-0" />
        <span className="font-display text-lg font-semibold tracking-tight">Pulse</span>
      </div>

      {project && (
        <div className="border-b border-hairline px-5 py-3">
          <div className="text-[10px] uppercase tracking-wide text-muted font-mono">Project</div>
          <div className="truncate text-sm font-medium">{project.name}</div>
        </div>
      )}

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive ? "bg-signal/10 text-signal" : "text-muted hover:bg-white/5 hover:text-ink"
              }`
            }
          >
            <Icon size={16} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-hairline px-5 py-4">
        <div className="truncate text-sm">{user?.full_name}</div>
        <div className="truncate text-xs text-muted">{user?.email}</div>
        <button
          onClick={logout}
          className="mt-3 flex items-center gap-2 text-xs text-muted hover:text-danger transition-colors"
        >
          <LogOut size={13} /> Sign out
        </button>
      </div>
    </aside>
  );
}
