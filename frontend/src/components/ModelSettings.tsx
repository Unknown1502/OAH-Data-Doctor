import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, post } from "../lib/api";
import { PROVIDER_PATHS } from "../lib/providerIcons";
import type { LlmConfig, LlmPreset, LlmProviders, LlmTest, Status } from "../lib/types";

// A user's own model settings live in this browser only: sessionStorage by default (gone when the tab closes), or
// localStorage when they tick "Keep me connected on this device". They are sent with that user's own requests to this
// Data Doctor server, which passes the key to the chosen provider for that one call and never stores or logs it.
const STORE = "dd-llm";
const OTHER = "__other__";

function load(): { config: LlmConfig; remember: boolean } | null {
  for (const [area, remember] of [["localStorage", true], ["sessionStorage", false]] as const) {
    try {
      const raw = window[area].getItem(STORE);
      if (raw) {
        const config = JSON.parse(raw) as LlmConfig;
        if (config && typeof config.provider === "string") return { config, remember };
      }
    } catch {
      /* storage unavailable or corrupt: behave as if nothing was saved */
    }
  }
  return null;
}

function persist(config: LlmConfig | null, remember: boolean) {
  for (const area of ["localStorage", "sessionStorage"] as const) {
    try {
      window[area].removeItem(STORE);
    } catch {
      /* ignore */
    }
  }
  if (!config) return;
  try {
    window[remember ? "localStorage" : "sessionStorage"].setItem(STORE, JSON.stringify(config));
  } catch {
    /* kept in memory for this page only */
  }
}

interface LlmCtx {
  /** The user's own settings, or null to use the server's. */
  config: LlmConfig | null;
  remember: boolean;
  /** The model that will answer: the user's, else the server default, else null (templates only). */
  activeName: string | null;
  /** Spread into request bodies of endpoints that may use a model. */
  body: { llm?: LlmConfig };
  save: (config: LlmConfig | null, remember: boolean) => void;
  open: () => void;
}

const Ctx = createContext<LlmCtx>({ config: null, remember: false, activeName: null, body: {}, save: () => {}, open: () => {} });
export const useLlm = () => useContext(Ctx);

export function LlmProvider({ status, children }: { status: Status | null; children: ReactNode }) {
  const [saved, setSaved] = useState(load);
  const [opened, setOpened] = useState(false);
  const save = useCallback((config: LlmConfig | null, remember: boolean) => {
    persist(config, remember);
    setSaved(config ? { config, remember } : null);
  }, []);
  const config = status?.llm_user_keys === false ? null : saved?.config ?? null;
  const value = useMemo<LlmCtx>(
    () => ({
      config,
      remember: saved?.remember ?? false,
      activeName: config ? `${config.provider}:${config.model}` : status?.llm_name ?? null,
      body: config ? { llm: config } : {},
      save,
      open: () => setOpened(true),
    }),
    [config, saved?.remember, status?.llm_name, save],
  );
  return (
    <Ctx.Provider value={value}>
      {children}
      {opened && <ModelDialog serverDefault={status?.llm_name ?? null} onClose={() => setOpened(false)} />}
    </Ctx.Provider>
  );
}

/** A provider's mark (Simple Icons, monochrome) or a lettermark where none is available. Decorative: the name is always shown. */
export function ProviderIcon({ id, className = "h-5 w-5" }: { id: string; className?: string }) {
  const d = PROVIDER_PATHS[id];
  if (d)
    return (
      <svg viewBox="0 0 24 24" className={`shrink-0 ${className}`} aria-hidden="true" fill="currentColor">
        <path d={d} />
      </svg>
    );
  const letter: Record<string, string> = { openai: "O", groq: "g" };
  if (letter[id])
    return (
      <svg viewBox="0 0 24 24" className={`shrink-0 ${className}`} aria-hidden="true">
        <circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <text x="12" y="16.4" textAnchor="middle" fontSize="12.5" fontWeight="700" fill="currentColor" style={{ fontFamily: "var(--font-sans)" }}>
          {letter[id]}
        </text>
      </svg>
    );
  return (
    <svg viewBox="0 0 24 24" className={`shrink-0 ${className}`} aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0V7ZM12 16v5" />
    </svg>
  );
}

const PROVIDER_LABEL: Record<string, string> = {
  groq: "Groq", gemini: "Google Gemini", openrouter: "OpenRouter", mistral: "Mistral", openai: "OpenAI",
  anthropic: "Claude", ollama: "Ollama", custom: "Custom endpoint",
};

/** "groq:llama-3.3-70b-versatile" -> { provider: "groq", label: "Groq", model: "llama-3.3-70b-versatile" }. */
export function describeModel(name: string) {
  const i = name.indexOf(":");
  const provider = i > 0 ? name.slice(0, i) : name;
  return { provider, label: PROVIDER_LABEL[provider] ?? provider, model: i > 0 ? name.slice(i + 1) : "" };
}

/** Which model is (or was) at work: provider mark, provider name and model, wherever a model touches the page. */
export function ModelBadge({ name, source }: { name: string; source?: "yours" | "server" }) {
  const { provider, label, model } = describeModel(name);
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-strong bg-sunk px-2.5 align-middle text-sm leading-7 text-ink">
      <ProviderIcon id={provider} className="h-3.5 w-3.5" />
      <span className="font-semibold">{label}</span>{" "}
      <span className="min-w-0 truncate text-ink-2">{model}</span>
      {source && <span className="sr-only">{source === "yours" ? " (your key)" : " (this server's setting)"}</span>}
    </span>
  );
}

/** Top-bar control: always shows which model (if any) is in use and whose key pays for it; opens the settings. */
export function ModelButton({ status }: { status: Status | null }) {
  const { activeName, config, open } = useLlm();
  if (!status?.llm_user_keys) return null;
  const d = activeName ? describeModel(activeName) : null;
  return (
    <button
      type="button"
      onClick={open}
      aria-haspopup="dialog"
      className="inline-flex max-w-[24rem] items-center gap-1.5 overflow-hidden rounded-lg border border-line-strong bg-panel px-3 py-1.5 text-sm text-ink-2 hover:bg-sunk hover:text-ink"
      title={d ? `${d.label} ${d.model}: ${config ? "your key" : "this server's setting"}. Select to change.` : "No language model: fixed templates only. Select to add one."}
    >
      {d ? (
        <>
          <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-algae" />
          <span className="sr-only">Language model: </span>
          <ProviderIcon id={d.provider} className="h-4 w-4 text-ink" />
          <span className="font-semibold text-ink">{d.label}</span>{" "}
          <span className="min-w-0 truncate">{d.model}</span>{" "}
          <span className="shrink-0 rounded-full bg-sunk px-1.5 text-xs text-ink-2">{config ? "your key" : "server"}</span>
        </>
      ) : (
        <>
          Language model: <span className="font-semibold text-ink">off</span>
        </>
      )}
    </button>
  );
}

function Chevrons() {
  return (
    <svg viewBox="0 0 16 16" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden="true"
      fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="m5 6 3-3 3 3M5 10l3 3 3-3" />
    </svg>
  );
}

function ModelDialog({ serverDefault, onClose }: { serverDefault: string | null; onClose: () => void }) {
  const { config, remember: wasRemembered, save } = useLlm();
  const ref = useRef<HTMLDialogElement>(null);
  const uid = useId();
  const [info, setInfo] = useState<LlmProviders | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [provider, setProvider] = useState(config?.provider ?? "");
  const [choice, setChoice] = useState(config?.model ?? "");
  const [otherModel, setOtherModel] = useState("");
  const [key, setKey] = useState(config?.api_key ?? "");
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? "");
  const [remember, setRemember] = useState(wasRemembered);
  const [live, setLive] = useState<{ forKey: string; models: string[] } | null>(null);
  const [listing, setListing] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [result, setResult] = useState<LlmTest | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    api<LlmProviders>("/llm/providers").then(
      (p) => {
        setInfo(p);
        // Preselect the saved provider, else the first (free) one, like a fresh "connect" screen.
        setProvider((cur) => cur || p.providers[0]?.id || "");
        setChoice((cur) => cur || p.providers[0]?.default_model || "");
      },
      (e: Error) => setLoadErr(e.message),
    );
  }, []);

  const preset: LlmPreset | null = info?.providers.find((p) => p.id === provider) ?? null;
  const needsKey = !!preset?.needs_key;
  const liveKey = `${provider}|${key.trim()}|${baseUrl.trim()}`;

  // As soon as a key is entered (or at once for a local model), list the models it can use.
  useEffect(() => {
    if (!preset || (needsKey && key.trim().length < 8) || (preset.id === "custom" && !baseUrl.trim())) return;
    let alive = true;
    const t = window.setTimeout(async () => {
      setListing(true);
      try {
        const body: LlmConfig = { provider: preset.id, model: "", api_key: key.trim() || undefined, base_url: baseUrl.trim() || undefined };
        const r = await post<{ models: string[]; error: string | null }>("/llm/models", body);
        if (alive) setLive({ forKey: liveKey, models: r.models });
      } catch {
        /* suggestions stay; Connect reports any real problem */
      } finally {
        if (alive) setListing(false);
      }
    }, 500);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [preset, needsKey, key, baseUrl, liveKey]);

  const liveModels = live?.forKey === liveKey ? live.models : [];
  const suggestions = preset?.models ?? [];
  const known = new Set([...suggestions, ...liveModels]);
  const extra = config?.provider === provider && config.model && !known.has(config.model) ? [config.model] : [];
  const model = choice === OTHER ? otherModel.trim() : choice;

  const chooseProvider = (id: string) => {
    const p = info?.providers.find((x) => x.id === id);
    setProvider(id);
    setChoice(p?.default_model || OTHER);
    setOtherModel("");
    setResult(null);
    setFormErr(null);
  };

  const problem = (): string | null => {
    if (!preset) return "Choose a provider.";
    if (preset.id === "custom" && !baseUrl.trim()) return "Enter the service's base URL.";
    if (!model) return "Choose a model, or enter its name.";
    if (needsKey && !key.trim()) return `Enter your ${preset.label} API key.`;
    return null;
  };

  const draft = (): LlmConfig => {
    const c: LlmConfig = { provider, model };
    if (key.trim()) c.api_key = key.trim();
    if (provider === "custom") c.base_url = baseUrl.trim();
    return c;
  };

  const connect = async (skipTest = false) => {
    const p = problem();
    setFormErr(p);
    setResult(null);
    if (p) return;
    if (skipTest) {
      save(draft(), remember);
      ref.current?.close();
      return;
    }
    setConnecting(true);
    try {
      const r = await post<LlmTest>("/llm/test", draft());
      if (r.ok) {
        save(draft(), remember);
        ref.current?.close();
        return;
      }
      setResult(r);
      if (r.models.length) setLive({ forKey: liveKey, models: r.models });
    } catch (e) {
      setResult({ ok: false, name: null, error: (e as Error).message, models: [] });
    } finally {
      setConnecting(false);
    }
  };

  const disconnect = () => {
    save(null, false);
    setKey("");
    setResult(null);
  };

  const field = "w-full rounded-lg border border-line-strong bg-chalk py-2.5 text-ink";
  const ready = !!preset && !!model && (!needsKey || !!key.trim()) && (preset.id !== "custom" || !!baseUrl.trim());

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={`${uid}-h`}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-xl border border-line bg-panel p-0 text-ink"
    >
      <form
        method="dialog"
        className="p-5 sm:p-6"
        onSubmit={(e) => {
          e.preventDefault();
          void connect();
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id={`${uid}-h`} className="m-0 text-xl font-bold tracking-tight">Connect a language model</h2>
          <button type="button" onClick={() => ref.current?.close()} aria-label="Close" className="-mr-1 -mt-1 rounded-md p-1 text-ink-3 hover:bg-sunk hover:text-ink">
            <svg viewBox="0 0 16 16" className="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
        <p className="mb-0 mt-1 text-sm text-ink-2">
          Optional. It rephrases findings and helps read typed claims; rules decide every verdict.
        </p>

        {config ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-algae/40 bg-algae-soft px-3 py-2 text-sm">
            <span className="inline-flex min-w-0 items-center gap-2 text-algae">
              <ProviderIcon id={config.provider} className="h-4 w-4" />
              <span className="truncate">Connected: <span className="font-semibold">{config.provider}:{config.model}</span></span>
            </span>
            <button type="button" onClick={disconnect} className="font-semibold text-ink underline underline-offset-2">Disconnect</button>
          </div>
        ) : (
          <p className="mb-0 mt-4 text-sm text-ink-3">
            Without your own key: {serverDefault ? `${serverDefault} (this server's setting)` : "fixed templates only"}.
          </p>
        )}

        {loadErr && <p role="alert" className="text-cinnabar">Could not load the providers ({loadErr}).</p>}

        <label className="mt-5 block font-semibold" htmlFor={`${uid}-p`}>Provider</label>
        <div className="relative mt-1.5">
          {preset && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"><ProviderIcon id={preset.id} /></span>}
          <select id={`${uid}-p`} value={provider} onChange={(e) => chooseProvider(e.target.value)} disabled={!info}
            className={`${field} appearance-none pl-11 pr-10`}>
            {info?.providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {p.free_tier && !p.label.includes("(") ? " (free tier)" : ""}
              </option>
            ))}
          </select>
          <Chevrons />
        </div>
        {preset?.note && <p className="mb-0 mt-1.5 text-sm text-ink-3">{preset.note}</p>}
        <p className="mb-0 mt-1 text-sm text-ink-3">
          {info?.allow_custom_url ? (
            provider !== "custom" && (
              <>
                Don't see your provider?{" "}
                <button type="button" onClick={() => chooseProvider("custom")} className="text-karst underline underline-offset-2">
                  Use any OpenAI-compatible service
                </button>
              </>
            )
          ) : (
            "Don't see your provider? Whoever runs this server can allow any OpenAI-compatible service."
          )}
        </p>

        {provider === "custom" && (
          <>
            <label className="mt-5 block font-semibold" htmlFor={`${uid}-u`}>Service base URL</label>
            <input id={`${uid}-u`} type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:1234/v1"
              className={`${field} mt-1.5 px-3`} autoComplete="off" spellCheck={false} />
          </>
        )}

        <label className="mt-5 block font-semibold" htmlFor={`${uid}-m`}>Model</label>
        <div className="relative mt-1.5">
          {preset && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"><ProviderIcon id={preset.id} /></span>}
          <select id={`${uid}-m`} value={choice} onChange={(e) => setChoice(e.target.value)} disabled={!preset}
            className={`${field} appearance-none pl-11 pr-10`}>
            {suggestions.length > 0 && (
              <optgroup label="Suggested">
                {suggestions.map((m) => <option key={m} value={m}>{m}{m === preset?.default_model ? " (default)" : ""}</option>)}
              </optgroup>
            )}
            {extra.map((m) => <option key={m} value={m}>{m}</option>)}
            {liveModels.length > 0 && (
              <optgroup label="Available with your key">
                {liveModels.filter((m) => !suggestions.includes(m)).map((m) => <option key={m} value={m}>{m}</option>)}
              </optgroup>
            )}
            <option value={OTHER}>Other model…</option>
          </select>
          <Chevrons />
        </div>
        {choice === OTHER && (
          <input aria-label="Model name" value={otherModel} onChange={(e) => setOtherModel(e.target.value)} placeholder="Exact model name"
            className={`${field} mt-2 px-3`} autoComplete="off" spellCheck={false} />
        )}
        <p className="mb-0 mt-1.5 text-sm text-ink-3" aria-live="polite">
          {preset?.kind === "ollama"
            ? listing ? "Looking up the installed models…" : liveModels.length > 0 ? `${liveModels.length} models are installed on this machine.` : ""
            : listing ? "Looking up the models your key can use…" : liveModels.length > 0 ? `${liveModels.length} models are available with your key.` : ""}
        </p>

        {(needsKey || provider === "custom") && preset && (
          <>
            <label className="mt-4 block font-semibold" htmlFor={`${uid}-k`}>API key{needsKey ? "" : " (if the service needs one)"}</label>
            <input id={`${uid}-k`} type="password" value={key} onChange={(e) => setKey(e.target.value)}
              placeholder={`Enter your ${preset.label} API key`} className={`${field} mt-1.5 px-3`} autoComplete="off" spellCheck={false}
              aria-describedby={`${uid}-where`} />
            {preset.key_url && (
              <p className="mb-0 mt-1.5 text-sm text-ink-3">
                Don't have one?{" "}
                <a href={preset.key_url} target="_blank" rel="noopener noreferrer" className="text-karst underline underline-offset-2">
                  Create a {preset.label} API key
                </a>
              </p>
            )}
          </>
        )}

        <label className="mt-5 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 accent-karst" />
          Keep me connected on this device
        </label>

        <button type="submit" disabled={!ready || connecting}
          className="mt-4 w-full rounded-lg border border-karst bg-karst px-4 py-2.5 font-semibold text-chalk hover:brightness-110 disabled:cursor-not-allowed disabled:border-line-strong disabled:bg-sunk disabled:text-ink-3">
          {connecting ? "Connecting…" : config ? "Save and reconnect" : "Connect"}
        </button>

        <div role="status" className="text-sm">
          {connecting && <p className="mb-0 mt-2 text-ink-2">Checking the key with one tiny request. A local model can take up to a minute the first time.</p>}
          {formErr && <p className="mb-0 mt-2 text-cinnabar">{formErr}</p>}
          {result && !result.ok && (
            <div className="mt-2 text-cinnabar">
              <p className="m-0">Could not connect: {result.error}</p>
              {result.models.length > 0 && <p className="m-0 mt-1 text-ink-2">Your key works with {result.models.length} models; choose one in Model.</p>}
              <button type="button" onClick={() => connect(true)} className="mt-1 text-ink-2 underline underline-offset-2">Save anyway</button>
            </div>
          )}
        </div>

        <p id={`${uid}-where`} className="mb-0 mt-4 text-center text-sm text-ink-3">
          {needsKey || provider === "custom" ? (
            <>
              Your key is saved in this browser only.{" "}
              <span className="block sm:inline">The server uses it for your requests and never stores or logs it.</span>
            </>
          ) : (
            "Your choice is saved in this browser only."
          )}
        </p>
      </form>
    </dialog>
  );
}
