import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, post } from "../lib/api";
import type { LlmConfig, LlmProviders, LlmTest, Status } from "../lib/types";
import { Button } from "./ui";

// A user's own model settings live in this browser only: sessionStorage by default (gone when the tab closes), or
// localStorage when they tick "Remember on this device". They are sent with that user's own requests to this Data Doctor
// server, which passes the key to the chosen provider for that one call and never stores or logs it.
const STORE = "dd-llm";

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
      {opened && <ModelDialog onClose={() => setOpened(false)} />}
    </Ctx.Provider>
  );
}

/** Top-bar control: shows which model (if any) rephrases findings, and opens the settings. */
export function ModelButton({ status }: { status: Status | null }) {
  const { activeName, config, open } = useLlm();
  if (!status?.llm_user_keys) return null;
  return (
    <button
      type="button"
      onClick={open}
      aria-haspopup="dialog"
      className="max-w-[18rem] truncate rounded-lg border border-line-strong bg-panel px-3 py-1.5 text-sm text-ink-2 hover:bg-sunk hover:text-ink"
      title={activeName ? `Language model: ${activeName}${config ? " (your settings)" : " (server setting)"}` : "Language model: off"}
    >
      Language model: <span className="font-semibold text-ink">{activeName ?? "off"}</span>
    </button>
  );
}

function ModelDialog({ onClose }: { onClose: () => void }) {
  const { config, remember: wasRemembered, save } = useLlm();
  const ref = useRef<HTMLDialogElement>(null);
  const uid = useId();
  const [info, setInfo] = useState<LlmProviders | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [provider, setProvider] = useState(config?.provider ?? "");
  const [model, setModel] = useState(config?.model ?? "");
  const [key, setKey] = useState(config?.api_key ?? "");
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? "");
  const [remember, setRemember] = useState(wasRemembered);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<LlmTest | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    api<LlmProviders>("/llm/providers").then(setInfo, (e: Error) => setLoadErr(e.message));
  }, []);

  const preset = info?.providers.find((p) => p.id === provider) ?? null;
  const draft = (): LlmConfig | null => {
    if (!preset) return null;
    const c: LlmConfig = { provider: preset.id, model: model.trim() || preset.default_model };
    if (key.trim()) c.api_key = key.trim();
    if (preset.id === "custom") c.base_url = baseUrl.trim();
    return c;
  };
  const problem = (): string | null => {
    if (!preset) return null;
    if (preset.needs_key && !key.trim()) return `Enter your ${preset.label} API key.`;
    if (preset.id === "custom" && !baseUrl.trim()) return "Enter the endpoint's base URL.";
    if (!(model.trim() || preset.default_model)) return "Enter a model name.";
    return null;
  };

  const runTest = async () => {
    const p = problem();
    setFormErr(p);
    setTest(null);
    const c = draft();
    if (p || !c) return;
    setTesting(true);
    try {
      setTest(await post<LlmTest>("/llm/test", c));
    } catch (e) {
      setTest({ ok: false, name: null, error: (e as Error).message, models: [] });
    } finally {
      setTesting(false);
    }
  };

  const onSave = () => {
    const p = problem();
    setFormErr(p);
    if (p) return;
    save(draft(), remember);
    ref.current?.close();
  };

  const onForget = () => {
    save(null, false);
    setProvider("");
    setKey("");
    setModel("");
    setBaseUrl("");
    setTest(null);
  };

  const choose = (id: string) => {
    setProvider(id);
    setModel("");
    setTest(null);
    setFormErr(null);
  };

  const field = "mt-1 w-full rounded-md border border-line-strong bg-chalk px-3 py-2 text-ink";
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={`${uid}-h`}
      className="m-auto w-[min(36rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-xl border border-line bg-panel p-0 text-ink"
    >
      <form
        method="dialog"
        className="p-5"
        onSubmit={(e) => {
          e.preventDefault();
          onSave();
        }}
      >
        <h2 id={`${uid}-h`} className="m-0 text-xl font-bold tracking-tight">Language model</h2>
        <p className="mt-2 text-ink-2">
          Optional. A model only rephrases findings and helps read typed claims. Rules decide every finding and verdict, with or without it.
        </p>

        {loadErr && <p role="alert" className="text-cinnabar">Could not load the provider list ({loadErr}).</p>}

        <label className="mt-4 block font-semibold" htmlFor={`${uid}-p`}>Provider</label>
        <select id={`${uid}-p`} value={provider} onChange={(e) => choose(e.target.value)} className={field} disabled={!info}>
          <option value="">This server's setting ({info?.server_default ?? "none: fixed templates only"})</option>
          {info?.providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
              {p.free_tier ? " (free)" : ""}
            </option>
          ))}
        </select>

        {preset && (
          <>
            <p className="mb-0 mt-2 text-sm text-ink-2">
              {preset.note}{" "}
              {preset.key_url && (
                <a href={preset.key_url} target="_blank" rel="noopener noreferrer" className="text-karst underline underline-offset-2">
                  Get a {preset.label} key
                </a>
              )}
            </p>

            {preset.id === "custom" && (
              <>
                <label className="mt-4 block font-semibold" htmlFor={`${uid}-u`}>Endpoint base URL</label>
                <input id={`${uid}-u`} type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:1234/v1" className={field} autoComplete="off" spellCheck={false} />
              </>
            )}

            <label className="mt-4 block font-semibold" htmlFor={`${uid}-m`}>Model</label>
            <input id={`${uid}-m`} value={model} onChange={(e) => setModel(e.target.value)} list={`${uid}-ml`}
              placeholder={preset.default_model || "model name"} className={field} autoComplete="off" spellCheck={false} />
            <datalist id={`${uid}-ml`}>{test?.models.map((m) => <option key={m} value={m} />)}</datalist>
            {preset.default_model && <p className="m-0 mt-1 text-sm text-ink-3">Leave empty for {preset.default_model}.</p>}

            {(preset.needs_key || preset.id === "custom") && (
              <>
                <label className="mt-4 block font-semibold" htmlFor={`${uid}-k`}>
                  API key{preset.needs_key ? "" : " (if the endpoint needs one)"}
                </label>
                <input id={`${uid}-k`} type="password" value={key} onChange={(e) => setKey(e.target.value)}
                  className={field} autoComplete="off" spellCheck={false} aria-describedby={`${uid}-priv`} />
              </>
            )}

            <label className="mt-4 flex items-center gap-2">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 accent-karst" />
              Remember on this device
            </label>
            <p className="m-0 mt-1 text-sm text-ink-3">Otherwise your settings are forgotten when you close this tab.</p>
          </>
        )}

        <p id={`${uid}-priv`} className="mt-4 rounded-lg bg-sunk px-3 py-2 text-sm text-ink-2">
          Your key stays in this browser. It is sent only with your own requests to this Data Doctor server, which passes it to the
          provider you chose for that one call. The server never stores it, never writes it to a log, and removes it from error
          messages.
        </p>

        {formErr && <p role="alert" className="m-0 mt-3 text-cinnabar">{formErr}</p>}
        <div role="status" className="mt-3 text-sm">
          {testing && <span className="text-ink-2">Testing… a local model can take up to a minute the first time.</span>}
          {test?.ok && (
            <span className="text-algae">
              Connected to {test.name} in {test.latency_ms} ms.
              {test.models.length > 0 && ` ${test.models.length} models are available in the Model list.`}
            </span>
          )}
          {test && !test.ok && (
            <span className="text-cinnabar">
              Could not use this model: {test.error}
              {test.models.length > 0 && ` This key can use ${test.models.length} models; pick one from the Model list.`}
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button kind="primary" type="submit">Save</Button>
          {preset && <Button onClick={runTest} disabled={testing}>{testing ? "Testing…" : "Test connection"}</Button>}
          {config && <Button kind="quiet" onClick={onForget}>Forget my settings</Button>}
          <Button kind="quiet" onClick={() => ref.current?.close()}>Close</Button>
        </div>
      </form>
    </dialog>
  );
}
