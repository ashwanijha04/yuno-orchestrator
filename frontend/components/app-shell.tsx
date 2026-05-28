"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Cockpit" },
  { href: "/workflows", label: "Workflows" },
  { href: "/runs", label: "Tasks" },
  { href: "/chat", label: "Chat" },
  { href: "/agents", label: "Agents" },
  { href: "/channels", label: "Channels" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => { setCollapsed(localStorage.getItem("nav:collapsed") === "1"); }, []);
  const toggle = () => setCollapsed((c) => { localStorage.setItem("nav:collapsed", c ? "0" : "1"); return !c; });

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="flex min-h-screen">
      {!collapsed && (
        <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div className="mb-8 px-2">
            <span className="font-mono text-lg font-semibold tracking-tight text-glow" style={{ color: "var(--color-primary)" }}>YUNO</span>
            <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">Agent Orchestration</p>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href}
                className={`rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive(item.href)
                    ? "bg-[var(--color-muted)] text-[var(--color-foreground)]"
                    : "text-[var(--color-muted-foreground)] hover:bg-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                }`}>
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] px-4">
          <div className="flex items-center gap-3">
            <button onClick={toggle} title={collapsed ? "Show sidebar" : "Hide sidebar"}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]">
              {collapsed ? "»" : "«"}
            </button>
            {collapsed && (
              <span className="font-mono text-sm font-semibold text-glow" style={{ color: "var(--color-primary)" }}>YUNO</span>
            )}
            <span className="text-sm text-[var(--color-muted-foreground)]">Local · single-user</span>
          </div>
          <HealthBadge />
        </header>
        <main className="flex-1 overflow-x-hidden overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}

function HealthBadge() {
  return (
    <span className="flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
      <span className="h-2 w-2 rounded-full hud-pulse bg-[var(--color-status-completed)]" />
      JARVIS ONLINE
    </span>
  );
}
