import {
  BookOpen,
  ClipboardCheck,
  Database,
  FileText,
  GitCompare,
  LayoutDashboard,
  Menu,
  Monitor,
  Moon,
  Search,
  ShieldCheck,
  Sun,
  SunMoon,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api, post } from "../lib/api";
import { when } from "../lib/format";
import type { Status } from "../lib/types";
import CommandPalette, { type Command } from "./CommandPalette";
import { LlmProvider, ModelButton, useLlm } from "./ModelSettings";

interface RunCtx {
  status: Status | null;
  runId: string | null;
  scan: (mode: "live" | "snapshot") => Promise<void>;
  scanning: boolean;
  scanError: string | null;
}
const Ctx = createContext<RunCtx>({ status: null, runId: null, scan: async () => {}, scanning: false, scanError: null });
export const useRun = () => useContext(Ctx);

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}
const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Investigate",
    items: [
      { to: "/", label: "Data health", icon: LayoutDashboard, end: true },
      { to: "/findings", label: "Findings", icon: TriangleAlert },
      { to: "/compare", label: "Compare", icon: GitCompare },
      { to: "/claims", label: "Check a claim", icon: ShieldCheck },
      { to: "/report", label: "Report", icon: FileText },
    ],
  },
  {
    label: "Data",
    items: [
      { to: "/data", label: "The data", icon: Database },
      { to: "/check", label: "Check your data", icon: ClipboardCheck },
      { to: "/sources", label: "Sources & rules", icon: BookOpen },
    ],
  },
];
const ALL_PAGES = NAV_GROUPS.flatMap((g) => g.items);
const MOBILE: NavItem[] = [
  { to: "/", label: "Health", icon: LayoutDashboard, end: true },
  { to: "/findings", label: "Findings", icon: TriangleAlert },
  { to: "/compare", label: "Compare", icon: GitCompare },
  { to: "/claims", label: "Claims", icon: ShieldCheck },
  { to: "/report", label: "Report", icon: FileText },
];

/** "3 min ago", from a timestamp the backend gave; the exact time is always one hover away. */
export function ago(iso: string | null | undefined, now: number): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return when(iso);
}

/** Apply and remember a colour scheme (dark, light or system); the theme control follows it. */
function setTheme(theme: string) {
  const root = document.documentElement;
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (theme === "system") {
    delete root.dataset.theme;
    meta?.setAttribute("content", "light dark");
  } else {
    root.dataset.theme = theme;
    meta?.setAttribute("content", theme);
  }
  try {
    localStorage.setItem("dd-theme", theme);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new CustomEvent("dd-theme", { detail: theme }));
}

const THEMES = [
  { id: "dark", label: "Dark", icon: Moon },
  { id: "light", label: "Light", icon: Sun },
  { id: "system", label: "System", icon: Monitor },
];

/** Icon-only theme control: a compact menu (Dark, Light, System), keyboard operable, remembered. */
function ThemeToggle() {
  const [theme, setLocal] = useState<string>(() => {
    try {
      return localStorage.getItem("dd-theme") ?? "dark";
    } catch {
      return "dark";
    }
  });
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const follow = (e: Event) => setLocal((e as CustomEvent<string>).detail);
    window.addEventListener("dd-theme", follow);
    return () => window.removeEventListener("dd-theme", follow);
  }, []);
  useEffect(() => {
    if (!open) return;
    wrap.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const away = (e: MouseEvent) => !wrap.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const onMenuKey = (e: React.KeyboardEvent) => {
    const items = [...(wrap.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])];
    const i = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      setOpen(false);
      button.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(i + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(i - 1 + items.length) % items.length]?.focus();
    }
  };
  return (
    <div ref={wrap} className="relative">
      <button
        ref={button}
        type="button"
        aria-label="Change theme"
        title="Change theme"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="grid h-8 w-8 place-items-center rounded-md text-ink-2 hover:bg-elevated hover:text-ink"
      >
        <SunMoon aria-hidden="true" size={17} />
      </button>
      {open && (
        <div role="menu" aria-label="Theme" onKeyDown={onMenuKey}
          className="absolute bottom-10 right-0 z-[var(--z-overlay)] w-40 rounded-lg border border-line bg-elevated p-1 shadow-[var(--shadow-overlay)]">
          {THEMES.map((t) => (
            <button
              key={t.id}
              type="button"
              role="menuitemradio"
              aria-checked={theme === t.id}
              onClick={() => {
                setTheme(t.id);
                setOpen(false);
                button.current?.focus();
              }}
              className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm ${theme === t.id ? "bg-karst-soft text-karst" : "text-ink hover:bg-sunk"}`}
            >
              <t.icon aria-hidden="true" size={15} />
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StageIcon({ state }: { state: "running" | "done" | "failed" }) {
  if (state === "done") return <span aria-hidden="true" className="inline-block w-4 text-center text-algae">✓</span>;
  if (state === "failed") return <span aria-hidden="true" className="inline-block w-4 text-center text-cinnabar">✕</span>;
  return <span aria-hidden="true" className="stage-running inline-block h-3 w-3 rounded-full border-2 border-karst border-t-transparent" />;
}

/** The audit as it happens: only stages the backend reported, never a made-up percentage. */
function ScanProgress({ status, onDismiss }: { status: Status; onDismiss: () => void }) {
  const [open, setOpen] = useState(false);
  const scan = status.scan;
  if (!scan?.stages?.length) return null;
  const done = !scan.running;
  const list = (
    <ol className="m-0 mt-2 grid list-none gap-x-6 gap-y-1 p-0 text-sm sm:grid-cols-2 xl:grid-cols-3" aria-live="polite">
      {scan.stages.map((s) => (
        <li key={s.id} className="flex min-w-0 items-baseline gap-2">
          <StageIcon state={s.state} />
          <span className="sr-only">{s.state === "done" ? "Done:" : s.state === "failed" ? "Failed:" : "In progress:"}</span>
          <span className={s.state === "running" ? "text-ink" : "text-ink-2"}>{s.label}</span>
          {s.detail && <span className="readout min-w-0 truncate text-xs text-ink-3" title={s.detail}>{s.detail}</span>}
        </li>
      ))}
    </ol>
  );
  if (done && !scan.error) {
    return (
      <div className="no-print border-b border-line px-5 py-1.5 text-sm lg:px-10">
        <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 text-ink-2">
          <span className="inline-flex items-center gap-1.5 text-ink">
            <span className="text-algae" aria-hidden="true">✓</span> Audit complete
          </span>
          <span className="hidden text-xs font-semibold uppercase tracking-[0.08em] text-ink-3 sm:inline">
            {status.source?.kind === "live" ? "Live data" : "Snapshot data"}
          </span>
          <span className="text-ink-3">{scan.stages.length} stages</span>
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="text-ink-2 underline decoration-line-strong underline-offset-2 hover:text-ink">
            {open ? "Hide the stages" : "Show the stages"}
          </button>
          <button type="button" onClick={onDismiss} className="text-ink-3 underline decoration-line-strong underline-offset-2 hover:text-ink">
            Dismiss
          </button>
        </p>
        {open && list}
      </div>
    );
  }
  return (
    <section aria-labelledby="scan-h" className="no-print border-b border-line bg-panel px-5 py-3 lg:px-10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="scan-h" className="m-0 text-sm font-semibold">
          {scan.running ? `Audit running (${scan.mode === "snapshot" ? "verified snapshot" : "live sandbox"})` : "Audit failed"}
        </h2>
        {done && (
          <button type="button" onClick={onDismiss} className="text-sm text-ink-2 underline underline-offset-2">
            Hide
          </button>
        )}
      </div>
      {list}
      {scan.error && <p className="m-0 mt-2 text-sm text-cinnabar">{scan.error}</p>}
    </section>
  );
}

/** Live or snapshot, in words and with a static dot: never inferred from colour alone. */
function SourceState({ status, now }: { status: Status | null; now: number }) {
  const src = status?.source;
  if (!src) return <span className="text-sm text-ink-3">No data loaded</span>;
  const live = src.kind === "live";
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1" title={`Fetched ${when(src.fetched_at)} from ${src.base_url}`}>
      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-bold uppercase tracking-[0.08em] ${live ? "border-algae/40 text-algae" : "border-karst/40 text-karst"}`}>
        <span aria-hidden="true" className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-algae" : "bg-karst"}`} />
        {live ? "Live" : "Snapshot"}
      </span>
      <span className="min-w-0 text-sm text-ink-2">
        {live ? (
          <><span className="hidden sm:inline">OAH FHIR sandbox <span aria-hidden="true" className="text-ink-3">·</span> </span>fetched {ago(src.fetched_at, now)}</>
        ) : (
          <>Captured {when(src.fetched_at)}{src.manifest_sha256 ? <><span aria-hidden="true" className="text-ink-3"> ·</span> sha256 verified</> : null}</>
        )}
      </span>
    </span>
  );
}

function SidebarNav({ onNavigate, idp = "nav" }: { onNavigate?: () => void; idp?: string }) {
  return (
    <nav aria-label="Main">
      {NAV_GROUPS.map((g, gi) => (
        <div key={g.label} className={gi ? "mt-7" : "mt-2"}>
          <p id={`${idp}-${g.label}`} className="m-0 px-3 pb-2 text-[0.78rem] font-bold uppercase tracking-[0.1em] text-ink-2">
            {g.label}
          </p>
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0" aria-labelledby={`${idp}-${g.label}`}>
            {g.items.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `group flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[0.92rem] no-underline transition-colors ${
                      isActive ? "bg-karst-soft font-semibold text-karst" : "font-medium text-ink hover:bg-elevated"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <n.icon aria-hidden="true" size={17} strokeWidth={1.8} className={isActive ? "text-karst" : "text-ink-3 group-hover:text-ink-2"} />
                      {n.label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarFooter({ status }: { status: Status | null }) {
  const src = status?.source;
  return (
    <div className="border-t border-line px-4 pb-4 pt-3 text-sm">
      <p className="m-0 flex items-center gap-2 text-ink">
        <span aria-hidden="true" className={`inline-block h-1.5 w-1.5 rounded-full ${src?.kind === "live" ? "bg-algae" : "bg-karst"}`} />
        {src ? `OAH FHIR sandbox, ${src.kind === "live" ? "live" : "snapshot"}` : "OAH FHIR sandbox"}
      </p>
      <p className="m-0 mt-1 text-xs text-ink-3">Independent hackathon project. Data: OneAquaHealth FHIR sandbox (HL7 Europe).</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1">
          <ModelButton status={status} />
        </span>
        <ThemeToggle />
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  return (
    <LlmProviderGate>
      <ShellInner>{children}</ShellInner>
    </LlmProviderGate>
  );
}

// Status is loaded once here and shared: the model settings and the shell both need it.
const StatusCtx = createContext<{ status: Status | null; refresh: () => Promise<Status | null> }>({ status: null, refresh: async () => null });

function LlmProviderGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const refresh = useCallback(async () => {
    try {
      const s = await api<Status>("/status");
      setStatus(s);
      return s;
    } catch {
      return null;
    }
  }, []);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const s = await refresh();
      if (!alive) return;
      timer.current = window.setTimeout(tick, s?.scan?.running ? 1500 : 15000);
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer.current);
    };
  }, [refresh]);
  return (
    <StatusCtx.Provider value={{ status, refresh }}>
      <LlmProvider status={status}>{children}</LlmProvider>
    </StatusCtx.Provider>
  );
}

function ShellInner({ children }: { children: ReactNode }) {
  const { status, refresh } = useContext(StatusCtx);
  const [scanError, setScanError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [palette, setPalette] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [hideProgress, setHideProgress] = useState<string | null>(null);
  const [hideFallback, setHideFallback] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const location = useLocation();
  const nav = useNavigate();
  const llm = useLlm();
  const main = useRef<HTMLElement>(null);
  const drawerRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(t);
  }, []);

  // Move focus to the main region on route change (SPA navigation announces the new page).
  useEffect(() => {
    main.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const d = drawerRef.current;
    if (!d) return;
    if (drawer && !d.open) d.showModal();
    else if (!drawer && d.open) d.close();
  }, [drawer]);

  const scan = useCallback(
    async (mode: "live" | "snapshot") => {
      setScanError(null);
      setRequested(true);
      setHideProgress(null);
      setHideFallback(false);
      try {
        await post("/audit", { source: mode });
      } catch (e) {
        setScanError((e as Error).message);
      } finally {
        setRequested(false);
        await refresh();
      }
    },
    [refresh],
  );

  const commands: Command[] = useMemo(
    () => [
      { label: "Run a live audit", hint: "reads the sandbox now", keywords: "scan refresh", run: () => void scan("live") },
      { label: "Switch to the verified snapshot", hint: "offline, sha256-checked", keywords: "offline", run: () => void scan("snapshot") },
      { label: "View critical findings", hint: "Findings", keywords: "severity", run: () => nav("/findings?severity=CRITICAL") },
      { label: "Compare two indicators", hint: "Compare", keywords: "comparability", run: () => nav("/compare") },
      { label: "Check a research claim", hint: "Claim guardrail", keywords: "claim", run: () => nav("/claims") },
      { label: "Open the report", hint: "Report", keywords: "export pdf download", run: () => nav("/report") },
      { label: "Check your own data", hint: "paste or drop FHIR", keywords: "upload", run: () => nav("/check") },
      { label: "Language model settings", hint: "optional", keywords: "ai llm key", run: () => llm.open() },
      { label: "Use the dark theme", hint: "appearance", keywords: "theme colour color", run: () => setTheme("dark") },
      { label: "Use the light theme", hint: "appearance", keywords: "theme colour color", run: () => setTheme("light") },
    ],
    [scan, nav, llm],
  );

  const scanning = requested || !!status?.scan?.running;
  const src = status?.source;
  const progressKey = status?.scan?.started_at ?? null;
  const showProgress = !!status?.scan?.stages?.length && (scanning || !!status.scan?.error || hideProgress !== progressKey);

  return (
    <Ctx.Provider value={{ status, runId: status?.run_id ?? null, scan, scanning, scanError }}>
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
        <aside className="no-print hidden border-r border-line bg-sidebar lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
          <div className="px-5 pb-3 pt-5">
            <NavLink to="/" className="flex items-center gap-2.5 text-ink no-underline">
              <img src="/favicon.svg" alt="" width={28} height={28} />
              <span className="text-[1.05rem] font-bold leading-tight tracking-tight">OAH Data Doctor</span>
            </NavLink>
            <p className="m-0 mt-1.5 text-sm leading-snug text-ink-2">Can you trust the evidence?</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
            <SidebarNav />
          </div>
          <SidebarFooter status={status} />
        </aside>

        <div className="min-w-0 pb-20 lg:pb-0">
          <header className="no-print flex items-center justify-between gap-3 border-b border-line bg-sidebar px-4 py-3 lg:hidden">
            <button type="button" onClick={() => setDrawer(true)} aria-label="Open the menu" className="grid h-9 w-9 place-items-center rounded-md text-ink hover:bg-elevated">
              <Menu aria-hidden="true" size={20} />
            </button>
            <NavLink to="/" className="flex min-w-0 items-center gap-2 text-ink no-underline">
              <img src="/favicon.svg" alt="" width={24} height={24} />
              <span className="truncate font-bold">OAH Data Doctor</span>
            </NavLink>
            <button type="button" onClick={() => setPalette(true)} aria-label="Search and commands" className="grid h-9 w-9 place-items-center rounded-md text-ink hover:bg-elevated">
              <Search aria-hidden="true" size={19} />
            </button>
          </header>

          <div className="no-print flex items-center justify-between gap-3 border-b border-line bg-chalk px-4 py-2.5 lg:px-10">
            <div className="min-w-0" aria-live="polite">
              <SourceState status={status} now={now} />
              {scanning && <span className="ml-3 text-sm text-karst">Audit running…</span>}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setPalette(true)} className="hidden items-center gap-2 rounded-md border border-line px-2.5 py-1.5 text-sm text-ink-2 hover:border-line-strong hover:text-ink lg:inline-flex">
                <Search aria-hidden="true" size={15} />
                Search
                <kbd className="readout rounded border border-line px-1 text-[0.7rem] text-ink-3">Ctrl K</kbd>
              </button>
              <button
                type="button"
                onClick={() => scan("live")}
                disabled={scanning}
                aria-label="Scan live sandbox"
                className="shrink-0 whitespace-nowrap rounded-md bg-karst px-3.5 py-1.5 text-sm font-semibold text-chalk hover:brightness-110 disabled:opacity-60"
              >
                Scan<span className="hidden sm:inline"> live sandbox</span>
              </button>
            </div>
          </div>
          {status && showProgress && <ScanProgress status={status} onDismiss={() => setHideProgress(progressKey)} />}
          {src?.fallback_reason && !hideFallback && (
            <div role="status" className="no-print flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-sulfur/40 bg-sulfur-soft px-5 py-2.5 text-sm lg:px-10">
              <span className="font-semibold text-sulfur">Live source unavailable.</span>
              <span className="text-ink">
                You are viewing the verified local snapshot of {when(src.fetched_at)}. {src.fallback_reason}
              </span>
              <span className="flex gap-3">
                <button type="button" onClick={() => scan("live")} disabled={scanning} className="font-semibold text-ink underline underline-offset-2">
                  Retry live
                </button>
                <button type="button" onClick={() => setHideFallback(true)} className="text-ink-2 underline underline-offset-2">
                  Continue with the snapshot
                </button>
              </span>
            </div>
          )}
          {scanError && (
            <div role="alert" className="border-b border-cinnabar/40 bg-cinnabar-soft px-5 py-2 text-sm text-cinnabar lg:px-10">
              {scanError}
            </div>
          )}
          <main id="content" ref={main} tabIndex={-1} className="mx-auto max-w-[1180px] px-5 py-8 outline-none lg:px-10">
            {children}
          </main>
          <footer className="mx-auto max-w-[1180px] px-5 pb-10 text-sm text-ink-3 lg:px-10">
            <p className="m-0 max-w-[80ch]">
              OAH Data Doctor is an independent project for the IEEE OneAquaHealth Global Hackathon 2026, not endorsed by OneAquaHealth,
              HL7 Europe or IEEE. It reads data only and never changes it. Verdicts are computed by deterministic rules; no AI decides a
              finding, comparison or claim.
            </p>
          </footer>
        </div>
      </div>

      <dialog ref={drawerRef} onClose={() => setDrawer(false)} aria-label="Menu"
        className="drawer-left m-0 h-dvh max-h-dvh w-[min(20rem,88vw)] border-0 border-r border-line bg-sidebar p-0 text-ink">
        {drawer && (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between px-5 pb-2 pt-4">
              <span className="font-bold">OAH Data Doctor</span>
              <button type="button" onClick={() => setDrawer(false)} aria-label="Close the menu" className="grid h-8 w-8 place-items-center rounded-md text-ink-2 hover:bg-elevated">
                <X aria-hidden="true" size={18} />
              </button>
            </div>
            <p className="m-0 px-5 pb-3 text-sm text-ink-2">Can you trust the evidence?</p>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
              <SidebarNav idp="drawer-nav" onNavigate={() => setDrawer(false)} />
            </div>
            <SidebarFooter status={status} />
          </div>
        )}
      </dialog>

      <nav aria-label="Main (mobile)" className="no-print fixed inset-x-0 bottom-0 z-[var(--z-nav)] border-t border-line bg-sidebar lg:hidden">
        <ul className="m-0 grid list-none grid-cols-5 p-0">
          {MOBILE.map((n) => (
            <li key={n.to}>
              <NavLink
                to={n.to}
                end={n.end}
                className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[0.72rem] no-underline ${isActive ? "font-semibold text-karst" : "text-ink-2"}`}
              >
                <n.icon aria-hidden="true" size={19} strokeWidth={1.8} />
                {n.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <CommandPalette open={palette} onClose={() => setPalette(false)} commands={commands} pages={ALL_PAGES} />
    </Ctx.Provider>
  );
}
