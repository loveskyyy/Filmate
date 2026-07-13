import { useEffect, useState } from "react";
import { ChevronDown, ExternalLink, Loader2, Search, SlidersHorizontal, X } from "lucide-react";
import type { PresetProvider } from "./types";

interface Props {
  open: boolean;
  mode?: "create" | "edit";
  presets: PresetProvider[];
  customSentinelId?: string;
  initial?: Partial<CredentialFormData>;
  onSubmit: (data: CredentialFormData) => Promise<void>;
  onClose: () => void;
  fetchApi: (path: string, options?: RequestInit) => Promise<Response>;
}

export interface CredentialFormData {
  preset_id: string;
  display_name: string;
  base_url: string;
  api_key: string;
  model: string;
  haiku_model: string;
  sonnet_model: string;
  opus_model: string;
  subagent_model: string;
}

export function AddCredentialModal({
  open,
  mode = "create",
  presets,
  customSentinelId = "__custom__",
  initial,
  onSubmit,
  onClose,
  fetchApi,
}: Props) {
  const [form, setForm] = useState<CredentialFormData>({
    preset_id: initial?.preset_id || presets[0]?.id || customSentinelId,
    display_name: initial?.display_name || presets[0]?.display_name || "",
    base_url: initial?.base_url || presets[0]?.messages_url || "",
    api_key: "",
    model: initial?.model || "",
    haiku_model: initial?.haiku_model || "",
    sonnet_model: initial?.sonnet_model || "",
    opus_model: initial?.opus_model || "",
    subagent_model: initial?.subagent_model || "",
  });

  const [advancedOpen, setAdvancedOpen] = useState(
    Boolean(initial?.haiku_model || initial?.sonnet_model || initial?.opus_model || initial?.subagent_model),
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setForm({
        preset_id: initial.preset_id || customSentinelId,
        display_name: initial.display_name || "",
        base_url: initial.base_url || "",
        api_key: "",
        model: initial.model || "",
        haiku_model: initial.haiku_model || "",
        sonnet_model: initial.sonnet_model || "",
        opus_model: initial.opus_model || "",
        subagent_model: initial.subagent_model || "",
      });
    } else if (presets.length > 0) {
      setForm({
        preset_id: presets[0].id,
        display_name: presets[0].display_name,
        base_url: presets[0].messages_url,
        api_key: "",
        model: "",
        haiku_model: "",
        sonnet_model: "",
        opus_model: "",
        subagent_model: "",
      });
    }
    setSubmitError(null);
    setModelOptions([]);
    setDiscoverError(null);
    setTestResult(null);
    setAdvancedOpen(Boolean(initial?.haiku_model || initial?.sonnet_model || initial?.opus_model || initial?.subagent_model));
  }, [open, initial, presets, customSentinelId]);

  const selectedPreset = presets.find((p) => p.id === form.preset_id);

  const handlePresetClick = (id: string) => {
    const preset = presets.find((p) => p.id === id);
    setForm((f) => ({
      ...f,
      preset_id: id,
      display_name: preset?.display_name || f.display_name,
      base_url: preset?.messages_url || f.base_url,
    }));
    setModelOptions([]);
  };

  const handleDiscover = async () => {
    if (!form.base_url || !form.api_key) {
      setDiscoverError("请先填写 Base URL 和 API Key");
      return;
    }
    setDiscovering(true);
    setDiscoverError(null);
    try {
      const res = await fetchApi("/api/v1/user-agent-config/discover", {
        method: "POST",
        body: JSON.stringify({
          discovery_format: "openai",
          base_url: form.base_url,
          api_key: form.api_key,
        }),
      });
      const data = await res.json();
      setModelOptions(data.models?.map((m: any) => m.id || m.model_id) || []);
      if (!data.models || data.models.length === 0) {
        setDiscoverError("未发现任何模型");
      }
    } catch (err: any) {
      setDiscoverError(err.message || "发现模型失败");
    } finally {
      setDiscovering(false);
    }
  };

  const handleTest = async () => {
    if (!form.api_key) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetchApi("/api/v1/agent/test-connection", {
        method: "POST",
        body: JSON.stringify({
          preset_id: form.preset_id,
          base_url: form.base_url || undefined,
          api_key: form.api_key,
          model: form.model || undefined,
        }),
      });
      const data = await res.json();
      setTestResult({ success: data.success || res.ok, message: data.message || "" });
    } catch (err: any) {
      setTestResult({ success: false, message: err.message || "连接失败" });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async () => {
    if (mode === "create" && !form.api_key) {
      setSubmitError("请填写 API Key");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit(form);
    } catch (err: any) {
      setSubmitError(err.message || "保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  const updateField = (key: keyof CredentialFormData, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setModelOptions([]);
    setTestResult(null);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto overscroll-contain rounded-xl border border-gray-200 bg-white p-5 shadow-xl">
        {/* Header */}
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="text-base font-medium text-gray-900">
            {mode === "edit" ? "编辑凭证" : "添加凭证"}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Preset grid */}
        <div className="mb-5">
          <div className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500">
            选择供应商
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <button
              type="button"
              onClick={() => handlePresetClick(customSentinelId)}
              disabled={mode === "edit"}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
                form.preset_id === customSentinelId
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-200 bg-gray-50 text-gray-700 hover:border-blue-300"
              }`}
            >
              自定义配置
            </button>
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePresetClick(p.id)}
                disabled={mode === "edit"}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  form.preset_id === p.id
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "border-gray-200 bg-gray-50 text-gray-700 hover:border-blue-300"
                }`}
              >
                {p.display_name}
              </button>
            ))}
          </div>
        </div>

        {/* Form */}
        <div className="space-y-4">
          {/* Display Name */}
          <div>
            <div className="mb-1 text-xs font-medium text-gray-700">显示名称</div>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) => updateField("display_name", e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Base URL */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-700">API Base URL</span>
            </div>
            <input
              type="url"
              value={form.base_url}
              onChange={(e) => updateField("base_url", e.target.value)}
              placeholder="https://api.example.com/anthropic"
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* API Key */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-700">API Key</span>
              {selectedPreset?.api_key_url && (
                <a
                  href={selectedPreset.api_key_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                >
                  获取 API Key
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => updateField("api_key", e.target.value)}
              placeholder={mode === "edit" ? "不填则保持不变" : "sk-ant-..."}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Default Model */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-700">默认模型</span>
              <button
                type="button"
                onClick={handleDiscover}
                disabled={discovering || !form.base_url || !form.api_key}
                className="inline-flex items-center gap-1 text-xs text-gray-500 transition hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {discovering ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Search className="h-3 w-3" />
                )}
                {discovering ? "发现中..." : "发现模型"}
              </button>
            </div>
            <select
              value={form.model}
              onChange={(e) => updateField("model", e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">请选择模型</option>
              {modelOptions.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            {discoverError && (
              <div className="mt-1 text-xs text-red-600">{discoverError}</div>
            )}
          </div>

          {/* Advanced Routing */}
          <details
            open={advancedOpen}
            onToggle={(e) => setAdvancedOpen(e.currentTarget.open)}
            className="rounded-lg border border-gray-200 bg-gray-50 p-3"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between">
              <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-600">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                高级模型路由
              </span>
              <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-gray-100 text-gray-500 ${advancedOpen ? "rotate-180" : ""}`}>
                <ChevronDown className="h-3 w-3" />
              </span>
            </summary>
            <p className="mt-2 text-xs text-gray-500">为 Haiku、Sonnet、Opus 等不同任务指定专用模型</p>
            <div className="mt-3 grid gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600">Haiku 模型</label>
                <select
                  value={form.haiku_model}
                  onChange={(e) => updateField("haiku_model", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                >
                  <option value="">默认</option>
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Sonnet 模型</label>
                <select
                  value={form.sonnet_model}
                  onChange={(e) => updateField("sonnet_model", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                >
                  <option value="">默认</option>
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Opus 模型</label>
                <select
                  value={form.opus_model}
                  onChange={(e) => updateField("opus_model", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                >
                  <option value="">默认</option>
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
          </details>

          {/* Test Result */}
          {testResult && (
            <div className={`rounded-lg p-3 text-sm ${testResult.success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {testResult.message}
            </div>
          )}

          {submitError && (
            <div className="text-sm text-red-600">{submitError}</div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-5 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || !form.api_key}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {testing ? "测试中..." : "测试连接"}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 transition hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting || (mode === "create" && !form.api_key)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "保存中..." : mode === "edit" ? "保存" : "添加"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
