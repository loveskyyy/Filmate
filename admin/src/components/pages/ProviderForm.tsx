import { useState, useCallback, useMemo, useRef, useEffect } from "react";
import { Loader2, Plus, Trash2, Eye, EyeOff, CheckCircle2, XCircle, Search, ChevronDown } from "lucide-react";

interface ModelRow {
  key: string;
  model_id: string;
  display_name: string;
  endpoint: string;
  is_default: boolean;
  is_enabled: boolean;
  price_unit: string;
  price_input: string;
  price_output: string;
  currency: string;
  resolution: string;
  supported_durations_text: string;
}

interface DiscoveredModel {
  id: string;
  display_name: string;
  endpoint: string;
  is_default: boolean;
}

function uid() {
  return Math.random().toString(36).substring(2, 9);
}

function newModelRow(): ModelRow {
  return {
    key: uid(),
    model_id: "",
    display_name: "",
    endpoint: "openai-chat",
    is_default: false,
    is_enabled: true,
    price_unit: "",
    price_input: "",
    price_output: "",
    currency: "USD",
    resolution: "",
    supported_durations_text: "",
  };
}

function discoveredToRow(d: DiscoveredModel): ModelRow {
  return {
    key: uid(),
    model_id: d.id,
    display_name: d.display_name || d.id,
    endpoint: d.endpoint || "openai-chat",
    is_default: d.is_default || false,
    is_enabled: true,
    price_unit: "",
    price_input: "",
    price_output: "",
    currency: "USD",
    resolution: "",
    supported_durations_text: "",
  };
}

interface ProviderFormProps {
  existing?: {
    id: number;
    discovery_format: string;
    display_name: string;
    base_url: string;
    image_max_workers: number | null;
    video_max_workers: number | null;
    audio_max_workers: number | null;
  } | null;
  onSaved: () => void;
  onCancel: () => void;
  forUserId: number;
  fetchApi: (path: string, options?: RequestInit) => Promise<Response>;
}

const DISCOVERY_FORMAT_OPTIONS = [
  { value: "openai", label: "OpenAI 兼容" },
  { value: "google", label: "Google AI 兼容" },
];

// Endpoint 选项（与后端 ENDPOINT_REGISTRY 一致）
interface EndpointOption {
  value: string;
  label: string;
  group: string;
  path: string;
  capability?: string;
}

const ENDPOINT_OPTIONS: EndpointOption[] = [
  // 文本
  { value: "openai-chat", label: "OpenAI 文本", group: "text", path: "/v1/chat/completions" },
  { value: "gemini-generate", label: "Gemini 文本", group: "text", path: "/v1beta/models/{model}:generateContent" },
  // 图片
  { value: "openai-images", label: "OpenAI 图片", group: "image", path: "/v1/images/{generations,edits}", capability: "文生图·图生图" },
  { value: "openai-images-generations", label: "OpenAI 图片（仅文生图）", group: "image", path: "/v1/images/generations", capability: "文生图" },
  { value: "openai-images-edits", label: "OpenAI 图片（仅图生图）", group: "image", path: "/v1/images/edits", capability: "图生图" },
  { value: "gemini-image", label: "Gemini 图片", group: "image", path: "/v1beta/models/{model}:generateContent", capability: "文生图·图生图" },
  { value: "dashscope-image", label: "阿里百炼（图片）", group: "image", path: "/api/v1/services/aigc/multimodal-generation/generation", capability: "文生图·图生图" },
  { value: "minimax-image", label: "MiniMax（图片）", group: "image", path: "/image_generation", capability: "文生图·图生图" },
  { value: "kling-image", label: "可灵 Kling（图片）", group: "image", path: "/v1/images/generations", capability: "文生图·图生图" },
  // 视频
  { value: "openai-video", label: "OpenAI 视频 (Sora)", group: "video", path: "/v1/videos" },
  { value: "newapi-video", label: "NewAPI 视频", group: "video", path: "/v1/video/generations" },
  { value: "v2-video", label: "V2 统一视频", group: "video", path: "/v2/video/generations" },
  { value: "ark-seedance", label: "火山方舟 (Seedance)", group: "video", path: "/api/v3/contents/generations/tasks" },
  { value: "vidu-video", label: "Vidu 视频", group: "video", path: "/ent/v2/img2video" },
  { value: "dashscope-async-video", label: "阿里百炼（异步视频）", group: "video", path: "/api/v1/services/aigc/video-generation/video-synthesis" },
  { value: "minimax-video", label: "MiniMax 海螺（视频）", group: "video", path: "/video_generation" },
  { value: "kling-video", label: "可灵 Kling（视频）", group: "video", path: "/v1/videos/{text2video,image2video,multi-image2video}" },
  // 语音
  { value: "openai-tts", label: "OpenAI 语音合成 (TTS)", group: "audio", path: "/v1/audio/speech" },
  // Embeddings
  { value: "openai-embeddings", label: "OpenAI Embeddings", group: "embeddings", path: "/v1/embeddings" },
  { value: "google-embeddings", label: "Google Embeddings", group: "embeddings", path: "/v1beta/models/{model}:embedContent" },
];

const IMAGE_RESOLUTIONS = ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"];
const VIDEO_RESOLUTIONS = ["720p", "1080p", "4k"];

function getMediaType(endpoint: string): string {
  if (endpoint.includes("chat") || endpoint.includes("text") || endpoint.includes("generate")) return "text";
  if (endpoint.includes("embeddings")) return "embeddings";
  if (endpoint.includes("image")) return "image";
  if (endpoint.includes("video")) return "video";
  if (endpoint.includes("tts") || endpoint.includes("audio")) return "audio";
  return "text";
}

function getEndpointLabel(value: string): string {
  const option = ENDPOINT_OPTIONS.find(o => o.value === value);
  return option?.label || value;
}

function getEndpointPath(value: string): string {
  const option = ENDPOINT_OPTIONS.find(o => o.value === value);
  return option?.path || "";
}

function getEndpointCapability(value: string): string {
  const option = ENDPOINT_OPTIONS.find(o => o.value === value);
  return option?.capability || "";
}

// 价格标签：不同媒体类型显示不同的单位
function getPriceLabels(media: string): { input: string; output: string } {
  if (media === "video") return { input: "$/秒", output: "" };
  if (media === "image") return { input: "$/张", output: "" };
  if (media === "audio") return { input: "$/万字符", output: "" };
  if (media === "embeddings") return { input: "$/1K tokens", output: "" };
  return { input: "$/M输入", output: "$/M输出" };
}

// 自定义 Endpoint 下拉组件
function EndpointSelect({ value, onChange, modelKey }: { value: string; onChange: (v: string) => void; modelKey: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const selected = ENDPOINT_OPTIONS.find(o => o.value === value);
  const groups = ["text", "image", "video", "audio", "embeddings"] as const;
  const groupLabels: Record<string, string> = { text: "文本", image: "图片", video: "视频", audio: "语音", embeddings: "Embeddings" };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`flex items-center justify-between gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-sm hover:border-gray-300 ${open ? "border-blue-400" : ""} w-48`}
      >
        <span>{selected?.label || value}</span>
        <ChevronDown className={`h-3 w-3 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-[500px] h-[400px] overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
          {groups.map(group => {
            const opts = ENDPOINT_OPTIONS.filter(o => o.group === group);
            if (opts.length === 0) return null;
            return (
              <div key={group}>
                <div className="px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-gray-400 bg-gray-50 border-b">
                  {groupLabels[group]}
                </div>
                {opts.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => { onChange(opt.value); setOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${opt.value === value ? "bg-blue-50 text-blue-700" : ""}`}
                  >
                    <div className="truncate font-medium">{opt.label}</div>
                    <div className="truncate text-xs text-gray-400">
                      <span>POST </span>
                      <span className="font-mono text-green-600">{opt.path}</span>
                      {opt.capability && <span className="ml-1 text-gray-500">{opt.capability}</span>}
                    </div>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ProviderForm({ existing, onSaved, onCancel, forUserId, fetchApi }: ProviderFormProps) {
  const isEdit = !!existing;

  const [displayName, setDisplayName] = useState(existing?.display_name ?? "");
  const [discoveryFormat, setDiscoveryFormat] = useState(existing?.discovery_format ?? "openai");
  const [baseUrl, setBaseUrl] = useState(existing?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [imageMaxWorkers, setImageMaxWorkers] = useState(existing?.image_max_workers?.toString() ?? "");
  const [videoMaxWorkers, setVideoMaxWorkers] = useState(existing?.video_max_workers?.toString() ?? "");
  const [audioMaxWorkers, setAudioMaxWorkers] = useState(existing?.audio_max_workers?.toString() ?? "");

  // Models state
  const [models, setModels] = useState<ModelRow[]>([]);
  const [modelFilter, setModelFilter] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filteredModels = useMemo(() => {
    if (!modelFilter.trim()) return models;
    const q = modelFilter.toLowerCase();
    return models.filter(
      (m) =>
        m.model_id.toLowerCase().includes(q) ||
        m.display_name.toLowerCase().includes(q),
    );
  }, [models, modelFilter]);

  const allFilteredEnabled = useMemo(
    () => filteredModels.length > 0 && filteredModels.every((m) => m.is_enabled),
    [filteredModels],
  );

  const baseUrlChanged = isEdit && baseUrl.trim() !== (existing?.base_url ?? "").trim();
  const useStoredCredential = isEdit && !apiKey && !baseUrlChanged;

  const handleDiscover = useCallback(async () => {
    if (!baseUrl.trim()) {
      setError("请填写 Base URL");
      return;
    }
    if (!useStoredCredential && !apiKey.trim()) {
      setError(baseUrlChanged ? "Base URL 已变更，请重新填写 API Key" : "请填写 API Key");
      return;
    }

    setDiscovering(true);
    setError(null);
    try {
      let res;
      if (useStoredCredential && existing) {
        res = await fetchApi(`/api/v1/user-agent-config/configs/${existing.id}/discover`, { method: "POST" });
      } else {
        res = await fetchApi(`/api/v1/user-agent-config/discover`, {
          method: "POST",
          body: JSON.stringify({ discovery_format: discoveryFormat, base_url: baseUrl, api_key: apiKey }),
        });
      }
      if (!res.ok) throw new Error("获取模型列表失败");
      const data = await res.json();
      const discovered = (data.models || []).map(discoveredToRow);
      setModels((prev) => {
        const existingKeys = new Set(prev.map((m) => m.model_id));
        const newModels = discovered.filter((d) => !existingKeys.has(d.model_id));
        return [...prev, ...newModels];
      });
      setModelFilter("");
    } catch (e: any) {
      setError(e.message || "获取模型列表失败");
    } finally {
      setDiscovering(false);
    }
  }, [discoveryFormat, baseUrl, apiKey, useStoredCredential, baseUrlChanged, existing, fetchApi]);

  const handleTest = useCallback(async () => {
    setTestResult(null);
    if (!baseUrl.trim()) {
      setError("请填写 Base URL");
      return;
    }
    if (!useStoredCredential && !apiKey.trim()) {
      setError(baseUrlChanged ? "Base URL 已变更，请重新填写 API Key" : "请填写 API Key");
      return;
    }

    setTesting(true);
    setError(null);
    try {
      let res;
      if (useStoredCredential && existing) {
        res = await fetchApi(`/api/v1/user-agent-config/configs/${existing.id}/test`, { method: "POST" });
      } else {
        res = await fetchApi(`/api/v1/user-agent-config/test`, {
          method: "POST",
          body: JSON.stringify({ discovery_format: discoveryFormat, base_url: baseUrl, api_key: apiKey }),
        });
      }
      const data = await res.json();
      setTestResult({ success: res.ok, message: data.message || (res.ok ? "连接成功" : "连接失败") });
    } catch (e: any) {
      setTestResult({ success: false, message: e.message || "连接测试失败" });
    } finally {
      setTesting(false);
    }
  }, [discoveryFormat, baseUrl, apiKey, useStoredCredential, baseUrlChanged, existing, fetchApi]);

  const handleSave = useCallback(async () => {
    console.log("handleSave called, isEdit:", isEdit, "existing:", existing);
    if (!displayName.trim()) {
      setError("请填写显示名称");
      return;
    }
    if (!baseUrl.trim()) {
      setError("请填写 Base URL");
      return;
    }
    const isUpdating = Boolean(isEdit && existing);
    if (isUpdating && !apiKey.trim()) {
      setError("请填写 API Key");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload: any = {
        discovery_format: discoveryFormat,
        display_name: displayName,
        base_url: baseUrl,
      };
      if (apiKey) payload.api_key = apiKey;
      if (imageMaxWorkers) payload.image_max_workers = parseInt(imageMaxWorkers);
      if (videoMaxWorkers) payload.video_max_workers = parseInt(videoMaxWorkers);
      if (audioMaxWorkers) payload.audio_max_workers = parseInt(audioMaxWorkers);

      console.log("Saving payload:", payload);

      const isUpdating = Boolean(isEdit && existing);
      const url = isUpdating
        ? `/api/v1/user-agent-config/configs/${existing!.id}?for_user_id=${forUserId}`
        : `/api/v1/user-agent-config/configs?for_user_id=${forUserId}`;
      console.log("Request URL:", url);

      const res = await fetchApi(url, {
        method: isUpdating ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      console.log("Response status:", res.status);

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `保存失败 (${res.status})`);
      }

      onSaved();
    } catch (e: any) {
      console.error("Save error:", e);
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }, [displayName, discoveryFormat, baseUrl, apiKey, imageMaxWorkers, videoMaxWorkers, audioMaxWorkers, isEdit, existing, forUserId, fetchApi, onSaved]);

  const updateModel = (key: string, patch: Partial<ModelRow>) => {
    setModels((prev) => prev.map((m) => (m.key === key ? { ...m, ...patch } : m)));
  };

  const removeModel = (key: string) => {
    setModels((prev) => prev.filter((m) => m.key !== key));
  };

  const addManualModel = () => {
    setModels((prev) => [...prev, newModelRow()]);
  };

  const toggleAllModels = () => {
    const targetKeys = new Set(filteredModels.map((m) => m.key));
    setModels((prev) =>
      prev.map((m) => (targetKeys.has(m.key) ? { ...m, is_enabled: !allFilteredEnabled } : m)),
    );
  };

  const toggleDefault = (key: string) => {
    const target = models.find((m) => m.key === key);
    if (!target) return;
    const media = getMediaType(target.endpoint);
    setModels((prev) =>
      prev.map((m) => {
        if (m.key === key) {
          return { ...m, is_default: !m.is_default };
        }
        // If enabling default on this model, disable others of same media type
        if (!m.is_default) return m;
        const otherMedia = getMediaType(m.endpoint);
        if (otherMedia === media && m.endpoint === target.endpoint) {
          return { ...m, is_default: false };
        }
        return m;
      }),
    );
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="mb-6">
        <div className="text-xs font-bold uppercase tracking-widest text-blue-600">
          {isEdit ? "EDIT PROVIDER" : "NEW PROVIDER"}
        </div>
        <h3 className="mt-1 text-xl font-light">
          {isEdit ? "编辑供应商" : "添加供应商"}
        </h3>
      </div>

      <div className="space-y-4">
        {/* Display name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            显示名称 *
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="例如: My OpenAI"
            className="w-full border rounded-lg px-3 py-2"
          />
        </div>

        {/* Base URL */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Base URL *
          </label>
          <input
            type="url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className="w-full border rounded-lg px-3 py-2"
          />
        </div>

        {/* API Key */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            API Key {isEdit ? "(不填则保持不变)" : "*"}
          </label>
          <div className="relative">
            <input
              type={showApiKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={isEdit ? "不填则保持不变" : "sk-..."}
              className="w-full border rounded-lg px-3 py-2 pr-10"
            />
            <button
              type="button"
              onClick={() => setShowApiKey((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Discovery format */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-bold uppercase tracking-wider text-gray-500">
            供应商格式
          </label>
          <select
            value={discoveryFormat}
            onChange={(e) => setDiscoveryFormat(e.target.value)}
            disabled={isEdit}
            className="rounded border border-gray-300 bg-gray-50 px-2 py-1 text-sm hover:border-gray-400 disabled:opacity-50"
          >
            {DISCOVERY_FORMAT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <span className="text-xs text-gray-400">发现模型列表使用的 API 格式</span>
        </div>

        {/* Discover button */}
        <div>
          <button
            type="button"
            onClick={handleDiscover}
            disabled={discovering}
            className="flex items-center gap-2 border border-gray-300 rounded-lg px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {discovering ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                发现模型中...
              </>
            ) : (
              "发现模型"
            )}
          </button>
        </div>

        {/* Models section */}
        {models.length > 0 && (
          <div className="border-t pt-4">
            <div className="mb-2 flex items-center gap-3">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-600">
                模型列表
              </span>
              {models.length > 1 && (
                <button
                  type="button"
                  onClick={toggleAllModels}
                  className="text-xs font-bold uppercase tracking-wider text-gray-500 hover:text-blue-600"
                >
                  {allFilteredEnabled ? "取消全选" : "全选"}
                </button>
              )}
            </div>

            {/* Model filter */}
            {models.length > 5 && (
              <div className="relative mb-3">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  placeholder="搜索模型..."
                  className="w-full border rounded py-1.5 pl-8 pr-3 text-sm"
                />
              </div>
            )}

            {/* Models list */}
            <div className="space-y-2">
              {filteredModels.map((m) => {
                const media = getMediaType(m.endpoint);
                const priceLabels = getPriceLabels(media);
                const showResolution = media === "image" || media === "video";
                const showDurations = media === "video";
                const endpointPath = getEndpointPath(m.endpoint);
                return (
                  <div key={m.key} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      {/* Enable toggle */}
                      <label className="flex cursor-pointer items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={m.is_enabled}
                          onChange={(e) => updateModel(m.key, { is_enabled: e.target.checked })}
                          className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300"
                        />
                      </label>

                      {/* Display Name */}
                      <input
                        type="text"
                        value={m.display_name}
                        onChange={(e) => updateModel(m.key, { display_name: e.target.value })}
                        placeholder="display-name"
                        className="w-48 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-sm placeholder:text-gray-400"
                      />

                      {/* Endpoint select */}
                      <EndpointSelect
                        value={m.endpoint}
                        onChange={(v) => updateModel(m.key, { endpoint: v, is_default: false })}
                        modelKey={m.key}
                      />

                      {/* Default toggle */}
                      <button
                        type="button"
                        onClick={() => toggleDefault(m.key)}
                        className={`rounded px-2 py-1 text-xs font-bold uppercase tracking-wider transition-colors ${
                          m.is_default
                            ? "bg-blue-100 text-blue-700 border border-blue-300"
                            : "bg-gray-100 text-gray-500 border border-gray-200"
                        }`}
                      >
                        默认
                      </button>

                      {/* Remove */}
                      <button
                        type="button"
                        onClick={() => removeModel(m.key)}
                        className="rounded p-1 text-gray-400 hover:text-red-500"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    {/* Pricing row */}
                    <div className="mt-2 flex flex-wrap items-center gap-2 pl-6 text-xs text-gray-500">
                      <select
                        value={m.currency}
                        onChange={(e) => updateModel(m.key, { currency: e.target.value })}
                        className="rounded border border-gray-200 bg-gray-50 px-1 py-0.5 text-xs"
                      >
                        <option value="USD">$</option>
                        <option value="CNY">¥</option>
                      </select>
                      <input
                        type="text"
                        value={m.price_input}
                        onChange={(e) => updateModel(m.key, { price_input: e.target.value })}
                        placeholder="0.00"
                        className="w-16 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
                      />
                      <span>{priceLabels.input}</span>
                      {priceLabels.output && (
                        <>
                          <span className="text-gray-300">|</span>
                          <input
                            type="text"
                            value={m.price_output}
                            onChange={(e) => updateModel(m.key, { price_output: e.target.value })}
                            placeholder="0.00"
                            className="w-16 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
                          />
                          <span>{priceLabels.output}</span>
                        </>
                      )}
                    </div>

                    {/* Resolution row（仅 image/video） */}
                    {showResolution && (
                      <div className="mt-2 flex items-center gap-2 pl-6">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-500 whitespace-nowrap">
                          分辨率
                        </span>
                        <select
                          value={m.resolution}
                          onChange={(e) => updateModel(m.key, { resolution: e.target.value })}
                          className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
                        >
                          <option value="">默认</option>
                          {media === "image"
                            ? IMAGE_RESOLUTIONS.map((r) => (
                                <option key={r} value={r}>{r}</option>
                              ))
                            : VIDEO_RESOLUTIONS.map((r) => (
                                <option key={r} value={r}>{r}</option>
                              ))}
                        </select>
                      </div>
                    )}

                    {/* Supported durations row（仅 video） */}
                    {showDurations && (
                      <div className="mt-2 flex items-center gap-2 pl-6">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-500 whitespace-nowrap">
                          支持时长
                        </span>
                        <input
                          type="text"
                          value={m.supported_durations_text}
                          onChange={(e) => updateModel(m.key, { supported_durations_text: e.target.value })}
                          placeholder="1-10, 15, 20"
                          className="flex-1 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
                        />
                        <span className="text-xs text-gray-400">如: 1-10, 15, 20</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Add manual model */}
            <button
              type="button"
              onClick={addManualModel}
              className="mt-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-gray-500 hover:text-blue-600"
            >
              <Plus className="h-3.5 w-3.5" />
              手动添加模型
            </button>
          </div>
        )}

        {/* Empty model hint */}
        {models.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-sm text-gray-500">
            点击上方「发现模型」自动获取可用模型，或
            <button
              type="button"
              onClick={addManualModel}
              className="ml-1 text-xs font-bold uppercase tracking-wider text-blue-600 hover:text-blue-700"
            >
              手动添加模型
            </button>
          </div>
        )}

        {/* Concurrency limits */}
        <div className="border-t pt-4">
          <div className="mb-1 text-xs font-bold uppercase tracking-wider text-blue-600">
            并发限制
          </div>
          <p className="mb-3 text-xs text-gray-500">设置各通道的最大并发工作数</p>
          <div className="flex flex-wrap gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">图片最大并发</label>
              <input
                type="number"
                min={1}
                value={imageMaxWorkers}
                onChange={(e) => setImageMaxWorkers(e.target.value)}
                placeholder="留空使用默认"
                className="w-32 border rounded px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">视频最大并发</label>
              <input
                type="number"
                min={1}
                value={videoMaxWorkers}
                onChange={(e) => setVideoMaxWorkers(e.target.value)}
                placeholder="留空使用默认"
                className="w-32 border rounded px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">音频最大并发</label>
              <input
                type="number"
                min={1}
                value={audioMaxWorkers}
                onChange={(e) => setAudioMaxWorkers(e.target.value)}
                placeholder="留空使用默认"
                className="w-32 border rounded px-3 py-2"
              />
            </div>
          </div>
        </div>

        {/* Test result */}
        {testResult && (
          <div
            className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${
              testResult.success
                ? "bg-green-50 text-green-700 border border-green-200"
                : "bg-red-50 text-red-700 border border-red-200"
            }`}
          >
            {testResult.success ? (
              <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
            ) : (
              <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
            )}
            <span>{testResult.message}</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 text-red-700 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Sticky actions */}
      <div className="sticky bottom-0 z-10 flex items-center gap-3 border-t bg-white px-6 py-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          {saving ? "保存中..." : "保存"}
        </button>

        <button
          type="button"
          onClick={handleTest}
          disabled={testing}
          className="border border-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
        >
          {testing && <Loader2 className="h-4 w-4 animate-spin" />}
          测试连接
        </button>

        <button
          type="button"
          onClick={onCancel}
          className="text-gray-500 hover:text-gray-700 px-3 py-2 text-sm"
        >
          取消
        </button>
      </div>
    </div>
  );
}
