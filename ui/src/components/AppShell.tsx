import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, ScrollText, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { getMeta } from "@/lib/api";

const NAV = [
  { to: "/", label: "Playground", icon: FlaskConical },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/config", label: "Config", icon: SlidersHorizontal },
];

function EngineDots() {
  const { data } = useQuery({ queryKey: ["meta"], queryFn: getMeta });
  if (!data) return null;
  const engines = Object.entries(data.engines);
  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span className="font-mono">v{data.version}</span>
      <div className="flex items-center gap-2">
        {engines.map(([name, loaded]) => (
          <span key={name} className="flex items-center gap-1" title={name}>
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                loaded ? "bg-primary" : "bg-muted-foreground/30",
              )}
            />
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur">
        <div className="flex w-full items-center gap-6 px-8 py-3">
          <img
            src="/logo.png"
            alt="GuardEx"
            className="h-9 w-auto shrink-0 select-none"
            draggable={false}
          />
          <nav className="flex gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <EngineDots />
          </div>
        </div>
      </header>
      <main className="w-full px-8 py-8">{children}</main>
    </div>
  );
}
