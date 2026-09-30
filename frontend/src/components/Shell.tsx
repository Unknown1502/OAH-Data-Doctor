import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api, post } from "../lib/api";
import { when } from "../lib/format";
import type { Status } from "../lib/types";
import { LlmProvider, ModelButton } from "./ModelSettings";
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

const NAV = [
  { to: "/", label: "Data health", end: true },
  { to: "/findings", label: "Findings" },
  { to: "/compare", label: "Compare" },
  { to: "/claims", label: "Check a claim" },
  { to: "/report", label: "Report" },
  { to: "/sources", label: "Sources and rules" },
];

function ThemeSelect() {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem("dd-theme") ?? "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
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
      if (theme === "system") localStorage.removeItem("dd-theme");
      else localStorage.setItem("dd-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  return (
    <label className="flex items-center gap-2 text-sm text-ink-2">
      Theme
      <select value={theme} onChange={(e) => setTheme(e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1 text-ink">
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const location = useLocation();
  const main = useRef<HTMLElement>(null);

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

  // Move focus to the main region on route change (SPA navigation announces the new page).
  useEffect(() => {
    main.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const scan = useCallback(
    async (mode: "live" | "snapshot") => {
      setScanError(null);
      setRequested(true);
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

  const scanning = requested || !!status?.scan?.running;
  const src = status?.source;

  return (
    <Ctx.Provider value={{ status, runId: status?.run_id ?? null, scan, scanning, scanError }}>
      <LlmProvider status={status}>
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
        <header className="border-b border-line bg-panel lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between gap-3 px-5 py-4 lg:block">
            <NavLink to="/" className="flex items-center gap-2.5 text-ink no-underline">
              <img src="/favicon.svg" alt="" width={30} height={30} />
              <span className="text-[1.15rem] font-bold leading-tight tracking-tight">
                OAH Data Doctor
              </span>
            </NavLink>
            <p className="m-0 hidden text-sm leading-snug text-ink-3 lg:mt-2 lg:block">
              Does published OneAquaHealth data make scientific sense?
            </p>
          </div>
          <nav aria-label="Main" className="overflow-x-auto px-3 pb-3 lg:pb-0">
            <ul className="m-0 flex list-none gap-1 p-0 lg:flex-col">
              {NAV.map((n) => (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    end={n.end}
                    className={({ isActive }) =>
                      `block whitespace-nowrap rounded-lg px-3 py-2 text-[0.97rem] no-underline ${
                        isActive ? "bg-karst-soft font-semibold text-karst" : "text-ink-2 hover:bg-sunk hover:text-ink"
                      }`
                    }
                  >
                    {n.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="hidden px-5 pt-6 text-sm text-ink-3 lg:block">
            <p className="m-0">Independent hackathon project. Data: OneAquaHealth FHIR sandbox (HL7 Europe).</p>
          </div>
        </header>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-chalk/90 px-5 py-3 backdrop-blur lg:px-10">
            <div className="flex flex-wrap items-center gap-3" aria-live="polite">
              <SourceBadge source={src} />
              {scanning && <span className="text-sm text-karst">Scanning the {status?.scan?.mode === "snapshot" ? "snapshot" : "live sandbox"}…</span>}
              {!scanning && status?.scan?.error && (
                <span className="text-sm text-cinnabar">Last live scan failed; showing {src?.kind === "live" ? "live" : "snapshot"} data.</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => scan("live")}
                disabled={scanning}
                className="rounded-lg border border-karst bg-karst px-3 py-1.5 text-sm font-semibold text-chalk disabled:opacity-60"
              >
                Scan live sandbox
              </button>
              <ModelButton status={status} />
              <ThemeSelect />
            </div>
          </div>
          {src?.fallback_reason && (
            <div role="status" className="border-b border-sulfur/40 bg-sulfur-soft px-5 py-2 text-sm text-sulfur lg:px-10">
              {src.fallback_reason} Snapshot taken {when(src.fetched_at)}.
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
      </LlmProvider>
    </Ctx.Provider>
  );
}
