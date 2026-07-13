// Agent credential types

export interface PresetProvider {
  id: string;
  display_name: string;
  icon_key: string;
  messages_url: string;
  discovery_url: string | null;
  default_model: string;
  suggested_models: string[];
  docs_url: string | null;
  api_key_url: string | null;
  is_recommended: boolean;
  notes?: string;
}

export interface AgentCredential {
  id: number;
  preset_id: string;
  display_name: string;
  icon_key: string | null;
  base_url: string;
  api_key_masked: string;
  model: string | null;
  haiku_model: string | null;
  sonnet_model: string | null;
  opus_model: string | null;
  subagent_model: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}
