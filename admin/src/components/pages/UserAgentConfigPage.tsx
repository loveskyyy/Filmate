import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Plus, Loader2, Bot, Film, Plug, AlertTriangle } from "lucide-react";
import { ProviderForm } from "./ProviderForm";
import { AddCredentialModal, type CredentialForm } from "../agent/AddCredentialModal";

type Section = "providers" | "agent" | "media";

// Provider config from user_agent_config table
interface ProviderConfig {
  id: number;
  user_id: number;
  discovery_format: string;
  display_name: string;
  base_url: string;
  api_key_masked: string;
  model: string | null;
  embedding_model: string | null;
  image_max_workers: number | null;
  video_max_workers: number | null;
  audio_max_workers: number | null;
  price_unit: string | null;
  price_input: number | null;
  price_output: number | null;
  currency: string | null;
  is_active: boolean;
  extra_config: Record<string, any> | null;
}

// Media settings
interface MediaSettings {
  default_video_backend: string;
  default_image_backend_t2i: string;
  default_image_backend_i2i: string;
  video_generate_audio: boolean;
  default_audio_backend: string;
  narration_voice: string;
  narration_speed: number | null;
  text_backend_script: string;
  text_backend_overview: string;
  text_backend_style: string;
}

// Runtime settings
interface RuntimeSettings {
  agent_session_cleanup_delay_seconds: number;
  agent_max_concurrent_sessions: number;
}

// System config options
interface SystemOptions {
  video_backends: string[];
  image_backends: string[];
  text_backends: string[];
  audio_backends: string[];
  provider_names: Record<string, string>;
}

// Full system config response
interface SystemConfigResponse {
  settings: MediaSettings;
  options: SystemOptions;
}

const VIDEO_OPTIONS = ["vidu", "kling", "minimax", "runway"];
const IMAGE_OPTIONS = ["dashscope", "openai"];
const TEXT_OPTIONS = ["openai", "anthropic"];

export default function UserAgentConfigPage() {
  const { userId } = useParams<{ userId: string }>();
  const [section, setSection] = useState<Section>("providers");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Provider configs (user_agent_config table)
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);

  // Agent credentials
  const [credentials, setCredentials] = useState<AgentCredential[]>([]);
  const [presets, setPresets] = useState<PresetProvider[]>([]);

  // Media settings
  const [mediaSettings, setMediaSettings] = useState<MediaSettings | null>(null);
  const [systemOptions, setSystemOptions] = useState<SystemOptions | null>(null);

  // Runtime settings
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings>({
    agent_session_cleanup_delay_seconds: 300,
    agent_max_concurrent_sessions: 5,
  });
  const [originalRuntimeSettings, setOriginalRuntimeSettings] = useState<RuntimeSettings>({
    agent_session_cleanup_delay_seconds: 300,
    agent_max_concurrent_sessions: 5,
  });

  // Provider form state (full-page form)
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<{
    id: number;
    discovery_format: string;
    display_name: string;
    base_url: string;
    image_max_workers: number | null;
    video_max_workers: number | null;
    audio_max_workers: number | null;
  } | null>(null);

  // Credential modal states
  const [showCredentialModal, setShowCredentialModal] = useState(false);
  const [editingCredential, setEditingCredential] = useState<AgentCredential | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchApi = (path: string, options?: RequestInit) => {
    const token = localStorage.getItem("admin_token");
    return fetch(path, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
  };

  useEffect(() => {
    const loadData = async () => {
      if (!userId) return;
      setLoading(true);
      setError(null);
      try {
        // Fetch all three tabs data in parallel
        const [configsRes, credsRes, presetsRes, mediaRes] = await Promise.all([
          fetchApi(`/api/v1/user-agent-config/configs?for_user_id=${userId}`),
          fetchApi(`/api/v1/agent/credentials?for_user_id=${userId}`),
          fetchApi(`/api/v1/agent/preset-providers`),
          fetchApi(`/api/v1/system/config`),
        ]);

        if (configsRes.status === 401 || credsRes.status === 401) {
          localStorage.removeItem("admin_token");
          window.location.href = "/login";
          return;
        }

        const [configsData, credsData, presetsData, mediaData] = await Promise.all([
          configsRes.ok ? configsRes.json() : [],
          credsRes.ok ? credsRes.json() : { credentials: [] },
          presetsRes.ok ? presetsRes.json() : { providers: [] },
          mediaRes.ok ? mediaRes.json() : null,
        ]);

        setConfigs(configsData || []);
        setCredentials(credsData?.credentials || []);
        setPresets(presetsData?.providers || []);
        
        // 设置 Media Settings
        if (mediaData?.settings) {
          setMediaSettings(mediaData.settings as MediaSettings);
        }
        // 设置 System Options（backend 列表）
        if (mediaData?.options) {
          setSystemOptions(mediaData.options as SystemOptions);
        }
        // Extract runtime settings from system config
        if (mediaData?.settings) {
          const runtime: RuntimeSettings = {
            agent_session_cleanup_delay_seconds: mediaData.settings.agent_session_cleanup_delay_seconds ?? 300,
            agent_max_concurrent_sessions: mediaData.settings.agent_max_concurrent_sessions ?? 5,
          };
          setRuntimeSettings(runtime);
          setOriginalRuntimeSettings(runtime);
        }
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [userId]);

  const handleDeleteConfig = async (configId: number) => {
    if (!confirm("确定删除此配置？")) return;
    try {
      const res = await fetchApi(`/api/v1/user-agent-config/configs/${configId}?for_user_id=${userId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("删除失败");
      setConfigs((prev) => prev.filter((c) => c.id !== configId));
    } catch (e: any) {
      alert(e.message);
    }
  };

  // Credential handlers
  const handleSaveCredential = async (form: CredentialForm) => {
    try {
      if (editingCredential) {
        // Update existing credential
        const updateData: any = {
          display_name: form.display_name,
          base_url: form.base_url,
        };
        if (form.model) updateData.model = form.model;
        if (form.api_key) updateData.api_key = form.api_key;
        if (form.haiku_model) updateData.haiku_model = form.haiku_model;
        if (form.sonnet_model) updateData.sonnet_model = form.sonnet_model;
        if (form.opus_model) updateData.opus_model = form.opus_model;
        if (form.subagent_model) updateData.subagent_model = form.subagent_model;

        const res = await fetchApi(`/api/v1/agent/credentials/${editingCredential.id}`, {
          method: "PATCH",
          body: JSON.stringify(updateData),
        });
        if (!res.ok) throw new Error("更新失败");
        const updatedCred = await res.json();
        setCredentials((prev) => prev.map((c) => (c.id === updatedCred.id ? updatedCred : c)));
      } else {
        // Create new credential
        const res = await fetchApi(`/api/v1/agent/credentials?for_user_id=${userId}`, {
          method: "POST",
          body: JSON.stringify({
            preset_id: form.preset_id,
            display_name: form.display_name,
            base_url: form.base_url,
            api_key: form.api_key,
            model: form.model,
            haiku_model: form.haiku_model || undefined,
            sonnet_model: form.sonnet_model || undefined,
            opus_model: form.opus_model || undefined,
            subagent_model: form.subagent_model || undefined,
          }),
        });
        if (!res.ok) throw new Error("创建失败");
        const newCred = await res.json();
        setCredentials((prev) => [...prev, newCred]);
      }
      setShowCredentialModal(false);
      setEditingCredential(null);
    } catch (e: any) {
      throw e; // Let modal handle the error
    }
  };

  const handleActivateCredential = async (credId: number) => {
    try {
      const res = await fetchApi(`/api/v1/agent/credentials/${credId}/activate`, { method: "POST" });
      if (!res.ok) throw new Error("激活失败");
      setCredentials((prev) =>
        prev.map((c) => ({ ...c, is_active: c.id === credId }))
      );
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDeleteCredential = async (credId: number) => {
    if (!confirm("确定删除此凭证？")) return;
    try {
      const res = await fetchApi(`/api/v1/agent/credentials/${credId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("删除失败");
      setCredentials((prev) => prev.filter((c) => c.id !== credId));
    } catch (e: any) {
      alert(e.message);
    }
  };

  // Media settings handlers
  const handleMediaChange = (key: keyof MediaSettings, value: any) => {
    setMediaSettings((prev) => prev ? { ...prev, [key]: value } : prev);
  };

  const handleSaveMedia = async () => {
    if (!mediaSettings) return;
    setSaving(true);
    try {
      const res = await fetchApi(`/api/v1/system/config`, {
        method: "PATCH",
        body: JSON.stringify(mediaSettings),
      });
      if (!res.ok) throw new Error("保存失败");
      alert("保存成功");
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveRuntime = async () => {
    setSaving(true);
    try {
      const res = await fetchApi(`/api/v1/system/config`, {
        method: "PATCH",
        body: JSON.stringify({
          agent_session_cleanup_delay_seconds: runtimeSettings.agent_session_cleanup_delay_seconds,
          agent_max_concurrent_sessions: runtimeSettings.agent_max_concurrent_sessions,
        }),
      });
      if (!res.ok) throw new Error("保存失败");
      setOriginalRuntimeSettings(runtimeSettings);
      alert("保存成功");
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  };

  const isRuntimeDirty = runtimeSettings.agent_session_cleanup_delay_seconds !== originalRuntimeSettings.agent_session_cleanup_delay_seconds ||
    runtimeSettings.agent_max_concurrent_sessions !== originalRuntimeSettings.agent_max_concurrent_sessions;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400 mr-2" />
        <span className="text-gray-500 text-sm">加载中</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Tab navigation */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setSection("providers")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${section === "providers" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
        >
          <Plug className="w-4 h-4" />
          供应商
        </button>
        <button
          onClick={() => setSection("agent")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${section === "agent" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
        >
          <Bot className="w-4 h-4" />
          智能体
        </button>
        <button
          onClick={() => setSection("media")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${section === "media" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
        >
          <Film className="w-4 h-4" />
          媒体模型
        </button>
      </div>

      {/* === PROVIDERS TAB === */}
      {section === "providers" && (
        <div>
          {showProviderForm ? (
            <ProviderForm
              existing={editingProvider}
              onSaved={() => {
                // Refresh configs
                setShowProviderForm(false);
                setEditingProvider(null);
                fetchApi(`/api/v1/user-agent-config/configs?for_user_id=${userId}`)
                  .then((r) => r.ok ? r.json() : [])
                  .then((data) => setConfigs(data || []));
              }}
              onCancel={() => {
                setShowProviderForm(false);
                setEditingProvider(null);
              }}
              forUserId={parseInt(userId || "0")}
              fetchApi={fetchApi}
            />
          ) : (
            <>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-medium">供应商配置</h2>
                <button
                  onClick={() => {
                    setEditingProvider(null);
                    setShowProviderForm(true);
                  }}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  添加供应商
                </button>
              </div>
              {configs.length === 0 ? (
                <div className="bg-white rounded-lg p-8 text-center text-gray-400">
                  <Plug className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>暂无供应商配置</p>
                </div>
              ) : (
                <div className="bg-white rounded-lg divide-y">
                  {configs.map((config) => (
                    <div key={config.id} className="p-4 flex items-center justify-between">
                      <div>
                        <div className="font-medium">{config.display_name}</div>
                        <div className="text-sm text-gray-500">{config.discovery_format} · {config.api_key_masked}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            setEditingProvider({
                              id: config.id,
                              discovery_format: config.discovery_format,
                              display_name: config.display_name,
                              base_url: config.base_url,
                              image_max_workers: config.image_max_workers,
                              video_max_workers: config.video_max_workers,
                              audio_max_workers: config.audio_max_workers,
                            });
                            setShowProviderForm(true);
                          }}
                          className="px-3 py-1 text-xs border border-blue-600 text-blue-600 rounded hover:bg-blue-50"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => handleDeleteConfig(config.id)}
                          className="px-3 py-1 text-xs border border-red-600 text-red-600 rounded hover:bg-red-50"
                        >
                          删除
                        </button>
                        <span className={`px-2 py-1 text-xs rounded ${config.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                          {config.is_active ? "启用" : "禁用"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* === AGENT TAB === */}
      {section === "agent" && (
        <div>
          {/* Credential Modal - using AddCredentialModal component */}
          <AddCredentialModal
            open={showCredentialModal}
            mode={editingCredential ? "edit" : "create"}
            presets={presets}
            initial={editingCredential ? {
              preset_id: editingCredential.preset_id,
              display_name: editingCredential.display_name,
              base_url: editingCredential.base_url,
              api_key: "",
              model: editingCredential.model || "",
              haiku_model: editingCredential.haiku_model || "",
              sonnet_model: editingCredential.sonnet_model || "",
              opus_model: editingCredential.opus_model || "",
              subagent_model: editingCredential.subagent_model || "",
            } : undefined}
            onSubmit={handleSaveCredential}
            onClose={() => { setShowCredentialModal(false); setEditingCredential(null); }}
            fetchApi={fetchApi}
          />

          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-medium">凭证配置</h2>
            <button
              onClick={() => {
                setEditingCredential(null);
                setShowCredentialModal(true);
              }}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              添加凭证
            </button>
          </div>
          {credentials.length === 0 ? (
            <div className="bg-white rounded-lg p-8 text-center text-gray-400">
              <Bot className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>暂无凭证</p>
            </div>
          ) : (
            <div className="bg-white rounded-lg divide-y">
              {credentials.map((cred) => (
                <div key={cred.id} className="p-4 flex items-center justify-between">
                  <div>
                    <div className="font-medium flex items-center gap-2">
                      {cred.display_name}
                      {cred.is_active && (
                        <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded">已激活</span>
                      )}
                    </div>
                    <div className="text-sm text-gray-500">{cred.preset_id} · {cred.api_key_masked}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setEditingCredential(cred);
                        setShowCredentialModal(true);
                      }}
                      className="px-3 py-1 text-xs border border-blue-600 text-blue-600 rounded hover:bg-blue-50"
                    >
                      编辑
                    </button>
                    {!cred.is_active && (
                      <button
                        onClick={() => handleActivateCredential(cred.id)}
                        className="px-3 py-1 text-xs border border-blue-600 text-blue-600 rounded hover:bg-blue-50"
                      >
                        激活
                      </button>
                    )}
                    <button
                      onClick={() => handleDeleteCredential(cred.id)}
                      className="px-3 py-1 text-xs border border-red-600 text-red-600 rounded hover:bg-red-50"
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Runtime Tuning Section */}
          <div className="border-t pt-6 mt-6">
            <div className="mb-4">
              <div className="text-xs font-bold uppercase tracking-widest text-blue-600">Runtime Tuning</div>
              <h3 className="text-xl font-light mt-1">高级设置</h3>
            </div>

            <div className="bg-white rounded-lg p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  会话清理延迟
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  智能体会话在无活动后多少秒被清理（10-3600）
                </p>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  value={runtimeSettings.agent_session_cleanup_delay_seconds}
                  onChange={(e) => setRuntimeSettings((prev) => ({
                    ...prev,
                    agent_session_cleanup_delay_seconds: Number(e.target.value) || 300,
                  }))}
                  className="w-32 border rounded px-3 py-2"
                />
                <span className="ml-2 text-sm text-gray-500">秒</span>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  最大并发会话数
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  允许同时运行的最大智能体会话数（1-20）
                </p>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={runtimeSettings.agent_max_concurrent_sessions}
                  onChange={(e) => setRuntimeSettings((prev) => ({
                    ...prev,
                    agent_max_concurrent_sessions: Number(e.target.value) || 5,
                  }))}
                  className="w-32 border rounded px-3 py-2"
                />
                <span className="ml-2 text-sm text-gray-500">个</span>
              </div>
            </div>

            {isRuntimeDirty && (
              <div className="flex justify-end gap-2 mt-4">
                <button
                  onClick={() => setRuntimeSettings(originalRuntimeSettings)}
                  className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  重置
                </button>
                <button
                  onClick={handleSaveRuntime}
                  disabled={saving}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  保存
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* === MEDIA TAB === */}
      {section === "media" && mediaSettings && systemOptions && (
        <div className="space-y-6">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-blue-600">默认路由</div>
            <h3 className="text-xl font-light mt-1">模型选择</h3>
            <p className="text-sm text-gray-500 mt-1">选择各频道使用的默认生成模型</p>
          </div>

          {/* Video */}
          <div className="bg-white rounded-lg p-5 space-y-4">
            <div>
              <div className="text-xs font-bold uppercase text-gray-400 mb-2">视频通道</div>
              <select
                value={mediaSettings.default_video_backend}
                onChange={(e) => handleMediaChange("default_video_backend", e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                <option value="">自动选择</option>
                {(systemOptions?.video_backends || []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                id="gen-audio"
                checked={mediaSettings.video_generate_audio}
                onChange={(e) => handleMediaChange("video_generate_audio", e.target.checked)}
                className="mt-1"
              />
              <label htmlFor="gen-audio" className="text-sm">
                <span>生成音频</span>
                <span className="block text-xs text-gray-400">支持该功能的后端自动生成背景音乐</span>
              </label>
            </div>
          </div>

          {/* Image */}
          <div className="bg-white rounded-lg p-5 space-y-4">
            <div>
              <div className="text-xs font-bold uppercase text-gray-400 mb-2">图片通道</div>
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-500 mb-1">文生图模型</label>
                <select
                  value={mediaSettings.default_image_backend_t2i}
                  onChange={(e) => handleMediaChange("default_image_backend_t2i", e.target.value)}
                  className="w-full border rounded px-3 py-2"
                >
                  <option value="">自动选择</option>
                  {(systemOptions?.image_backends || []).map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">图生图模型</label>
                <select
                  value={mediaSettings.default_image_backend_i2i}
                  onChange={(e) => handleMediaChange("default_image_backend_i2i", e.target.value)}
                  className="w-full border rounded px-3 py-2"
                >
                  <option value="">自动选择</option>
                  {(systemOptions?.image_backends || []).map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Text */}
          <div className="bg-white rounded-lg p-5 space-y-4">
            <div className="text-xs font-bold uppercase text-gray-400">文本通道</div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase mb-1">脚本生成</label>
              <select
                value={mediaSettings.text_backend_script}
                onChange={(e) => handleMediaChange("text_backend_script", e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                <option value="">自动选择</option>
                {(systemOptions?.text_backends || []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase">概述生成</label>
              <select
                value={mediaSettings.text_backend_overview}
                onChange={(e) => handleMediaChange("text_backend_overview", e.target.value)}
                className="w-full border rounded px-3 py-2 mt-1"
              >
                <option value="">自动选择</option>
                {(systemOptions?.text_backends || []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase">风格分析</label>
              <select
                value={mediaSettings.text_backend_style}
                onChange={(e) => handleMediaChange("text_backend_style", e.target.value)}
                className="w-full border rounded px-3 py-2 mt-1"
              >
                <option value="">自动选择</option>
                {(systemOptions?.text_backends || []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Audio */}
          <div className="bg-white rounded-lg p-5 space-y-4">
            <div className="text-xs font-bold uppercase text-gray-400">语音通道</div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase mb-1">语音合成</label>
              <select
                value={mediaSettings.default_audio_backend}
                onChange={(e) => handleMediaChange("default_audio_backend", e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                <option value="">自动选择</option>
                {(systemOptions?.audio_backends || []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase mb-1">语音标识符</label>
              <input
                type="text"
                value={mediaSettings.narration_voice || ""}
                onChange={(e) => handleMediaChange("narration_voice", e.target.value)}
                placeholder="voice-xxx"
                className="w-full border rounded px-3 py-2"
              />
              <p className="text-xs text-gray-400 mt-1">指定使用的语音标识符</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase mb-1">语速</label>
              <input
                type="number"
                step="0.1"
                value={mediaSettings.narration_speed ?? ""}
                onChange={(e) => handleMediaChange("narration_speed", e.target.value ? Number(e.target.value) : null)}
                placeholder="1.0"
                className="w-full border rounded px-3 py-2"
              />
              <p className="text-xs text-gray-400 mt-1">语速倍率，如 1.0 / 1.5 / 2.0</p>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={handleSaveMedia}
              disabled={saving}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm flex items-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              保存
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
