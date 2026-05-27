import Link from "next/link";

const NAV = [
  { href: "/", label: "Cockpit" },
  { href: "/orchestrate", label: "Orchestrate" },
  { href: "/runs", label: "Tasks" },
  { href: "/chat", label: "Chat" },
  { href: "/agents", label: "Agents" },
  { href: "/workflows", label: "Workflows" },
  { href: "/channels", label: "Channels" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-card)] p-4">
        <div className="mb-8 px-2">
          <span className="font-mono text-lg font-semibold tracking-tight text-glow" style={{ color: "var(--color-primary)" }}>YUNO</span>
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted-foreground)]">
            Agent Orchestration
          </p>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] px-6">
          <span className="text-sm text-[var(--color-muted-foreground)]">
            Local · single-user
          </span>
          <HealthBadge />
        </header>
        <main className="flex-1 overflow-auto p-6">{children}</main>
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
