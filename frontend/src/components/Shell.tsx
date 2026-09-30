import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api, post } from "../lib/api";
import { when } from "../lib/format";
import type { Status } from "../lib/types";
import CommandPalette, { type Command } from "./CommandPalette";
import { LlmProvider, ModelButton, useLlm } from "./ModelSettings";
import { SourceBadge } from "./ui";

interface RunCtx {
  status: Status | null;
  runId: string | null;
  scan: (mode: "live" | "snapshot") => Promise<void>;
  scanning: boolean;
  scanError: string | null;
}
const Ctx = createContext<RunCtx>({ status: null, runId: null, scan: async () => {}, scanning: false, scanError: null });
export const useRun = () => useContext(Ctx);

const NAV_GROUPS = [
  {
    label: "Investigate",
    items: [
      { to: "/", label: "Data health", end: true },
      { to: "/findings", label: "Findings" },
      { to: "/compare", label: "Compare" },
      { to: "/claims", label: "Check a claim" },
      { to: "/report", label: "Report" },
    ],
  },
  {
    label: "Data",
    items: [
      { to: "/data", label: "The data" },
      { to: "/check", label: "Check your data" },
      { to: "/sources", label: "Sources and rules" },
    ],
  },
];
const ALL_PAGES = NAV_GROUPS.flatMap((g) => g.items);

// Mobile: the five steps of an investigation, plus search for everything else.
const MOBILE = [
  { to: "/", label: "Home", end: true, d: "M3 10.5 12 4l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { to: "/findings", label: "Findings", d: "M12 3 3 19h18L12 3zM12 10v4M12 17v.5" },
  { to: "/compare", label: "Compare", d: "M7 7h13M17 4l3 3-3 3M17 17H4M7 14l-3 3 3 3" },
  { to: "/claims", label: "Claims", d: "M5 4h14v12H9l-4 4zM9 9h6M9 12h4" },
  { to: "/report", label: "Report", d: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7" },
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

/** Apply and remember a colour scheme (dark, light or system); the Theme control follows it. */
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

function ThemeSelect() {
  const [theme, setLocal] = useState<string>(() => {
    try {
      return localStorage.getItem("dd-theme") ?? "dark";
    } catch {
      return "dark";
    }
  });
  useEffect(() => {
    const follow = (e: Event) => setLocal((e as CustomEvent<string>).detail);
    window.addEventListener("dd-theme", follow);
    return () => window.removeEventListener("dd-theme", follow);
  }, []);
  return (
    <label className="flex items-center gap-2 text-sm text-ink-2">
      Theme
      <select value={theme} onChange={(e) => setTheme(e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1 text-ink">
        <option value="dark">Dark</option>
        <option value="light">Light</option>
        <option value="system">System</option>
      </select>
    </label>
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
          {s.detail && <span className="min-w-0 truncate text-ink-3" title={s.detail}>{s.detail}</span>}
        </li>
      ))}
    </ol>
  );
  if (done && !scan.error) {
    return (
      <div className="no-print border-b border-line bg-panel px-5 py-2 text-sm lg:px-10">
        <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-ink-2">
          <span>
            <span className="text-algae" aria-hidden="true">✓</span> Audit complete
            {status.source ? `: ${status.source.kind === "live" ? "live data" : "snapshot data"}` : ""}, {scan.stages.length} stages.
          </span>
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="underline underline-offset-2">
            {open ? "Hide the stages" : "Show the stages"}
          </button>
          <button type="button" onClick={onDismiss} className="text-ink-3 underline underline-offset-2">
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
          {scan.running
            ? `Audit running (${scan.mode === "snapshot" ? "verified snapshot" : "live sandbox"})`
            : scan.error
              ? "Audit failed"
              : `Audit complete${status.source ? `: ${status.source.kind === "live" ? "live data" : "snapshot data"}` : ""}`}
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
  const [hideProgress, setHideProgress] = useState<string | null>(null);
  const [hideFallback, setHideFallback] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const location = useLocation();
  const nav = useNavigate();
  const llm = useLlm();
  const main = useRef<HTMLElement>(null);

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
      <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
        <header className="no-print border-b border-line bg-panel lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between gap-3 px-5 py-4 lg:block">
            <NavLink to="/" className="flex items-center gap-2.5 text-ink no-underline">
              <img src="/favicon.svg" alt="" width={30} height={30} />
              <span className="text-[1.1rem] font-bold leading-tight tracking-tight">OAH Data Doctor</span>
            </NavLink>
            <p className="m-0 hidden text-sm leading-snug text-ink-3 lg:mt-2 lg:block">Can you trust the evidence?</p>
            <button type="button" onClick={() => setPalette(true)} className="rounded-md border border-line px-2.5 py-1 text-sm text-ink-2 lg:hidden" aria-label="Search and commands">
              Search
            </button>
          </div>
          <nav aria-label="Main" className="hidden px-3 lg:block">
            {NAV_GROUPS.map((g) => (
              <div key={g.label} className="mb-4">
                <p className="m-0 px-3 pb-1 text-xs font-semibold text-ink-3">{g.label}</p>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
                  {g.items.map((n) => (
                    <li key={n.to}>
                      <NavLink
                        to={n.to}
                        end={"end" in n ? n.end : undefined}
                        className={({ isActive }) =>
                          `block rounded-lg px-3 py-1.5 text-[0.96rem] no-underline ${
                            isActive ? "bg-karst-soft font-semibold text-karst" : "text-ink-2 hover:bg-sunk hover:text-ink"
                          }`
                        }
                      >
                        {n.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          <div className="mt-auto hidden px-5 pb-5 text-sm text-ink-3 lg:block">
            <p className="m-0 flex items-center gap-2">
              <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${src?.kind === "live" ? "bg-algae" : "bg-karst"}`} />
              {src ? (src.kind === "live" ? "OAH FHIR sandbox, live" : "Verified snapshot") : "Loading"}
            </p>
            <p className="m-0 mt-2">Independent hackathon project. Data: OneAquaHealth FHIR sandbox (HL7 Europe).</p>
            <div className="mt-3">
              <ThemeSelect />
            </div>
          </div>
        </header>

        <div className="min-w-0 pb-20 lg:pb-0">
          <div className="no-print flex flex-wrap items-center justify-between gap-3 border-b border-line bg-chalk/90 px-5 py-3 backdrop-blur lg:px-10">
            <div className="flex flex-wrap items-center gap-3" aria-live="polite">
              <SourceBadge source={src} compact />
              {src && (
                <span className="text-sm text-ink-2" title={`Fetched ${when(src.fetched_at)} from ${src.base_url}`}>
                  {src.kind === "live"
                    ? `OAH FHIR sandbox, fetched ${ago(src.fetched_at, now)}`
                    : `of ${when(src.fetched_at)}${src.manifest_sha256 ? ", sha256 verified" : ""}`}
                </span>
              )}
              {scanning && <span className="text-sm text-karst">Audit running…</span>}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => setPalette(true)} className="hidden items-center gap-2 rounded-lg border border-line-strong bg-panel px-3 py-1.5 text-sm text-ink-2 hover:bg-sunk lg:inline-flex">
                Search
                <kbd className="readout rounded border border-line px-1 text-xs">Ctrl K</kbd>
              </button>
              <button
                type="button"
                onClick={() => scan("live")}
                disabled={scanning}
                className="rounded-lg border border-karst bg-karst px-3 py-1.5 text-sm font-semibold text-chalk disabled:opacity-60"
              >
                Scan live sandbox
              </button>
              <span className="hidden md:inline-flex">
                <ModelButton status={status} />
              </span>
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

      <nav aria-label="Main (mobile)" className="no-print fixed inset-x-0 bottom-0 z-20 border-t border-line bg-panel lg:hidden">
        <ul className="m-0 grid list-none grid-cols-6 p-0">
          {MOBILE.map((n) => (
            <li key={n.to}>
              <NavLink
                to={n.to}
                end={n.end}
                className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[0.72rem] no-underline ${isActive ? "font-semibold text-karst" : "text-ink-2"}`}
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d={n.d} />
                </svg>
                {n.label}
              </NavLink>
            </li>
          ))}
          <li>
            <button type="button" onClick={() => setPalette(true)} className="flex w-full flex-col items-center gap-0.5 py-2 text-[0.72rem] text-ink-2">
              <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                <circle cx="11" cy="11" r="6.5" />
                <path d="m16 16 4.5 4.5" />
              </svg>
              More
            </button>
          </li>
        </ul>
      </nav>

      <CommandPalette open={palette} onClose={() => setPalette(false)} commands={commands} pages={ALL_PAGES} />
    </Ctx.Provider>
  );
}
