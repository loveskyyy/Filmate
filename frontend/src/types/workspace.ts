export type ProjectEventSource = "webui" | "worker" | "filesystem";

export interface ProjectChangeFocus {
  pane: "characters" | "scenes" | "props" | "episode";
  episode?: number;
  // segment/drama_scene/shot 三种骨架条目走时间线画布，锚点类型统一为 segment；video_units 走参考
  // 生视频画布，锚点类型为 reference_unit（与 WorkspaceFocusTarget["type"] 及画布守卫对齐）。
  anchor_type?: "character" | "scene" | "prop" | "segment" | "reference_unit" | "script";
  anchor_id?: string;
  tab?: string;
}

export interface ProjectChange {
  // segment/drama_scene/shot/reference_unit 为四种剧本骨架条目类型（narration/drama/ad/参考生视频），
  // 驱动分组标签映射；drama 用 drama_scene 避免与命名实体 scene 撞组。
  entity_type:
    | "project"
    | "character"
    | "scene"
    | "prop"
    | "segment"
    | "drama_scene"
    | "shot"
    | "reference_unit"
    | "episode"
    | "overview"
    | "draft"
    | "grid";
  action:
    | "created"
    | "updated"
    | "deleted"
    | "storyboard_ready"
    | "video_ready"
    | "grid_ready"
    | "script_generated"
    | "script_deleted";
  entity_id: string;
  label: string;
  script_file?: string;
  episode?: number;
  focus?: ProjectChangeFocus | null;
  important: boolean;
  asset_fingerprints?: Record<string, number>;
}

export interface ProjectChangeBatchPayload {
  project_name: string;
  batch_id: string;
  fingerprint: string;
  generated_at: string;
  source: ProjectEventSource;
  changes: ProjectChange[];
}

export interface ProjectEventSnapshotPayload {
  project_name: string;
  fingerprint: string;
  generated_at: string;
}

/** 项目事件流终止事件负载——项目目录被删除后下发，随后流正常结束。 */
export interface ProjectDeletedPayload {
  project_name: string;
}

// 由后端 ``ProjectEventService._do_broadcast_script_saved`` 在 ``save_script`` 写盘后
// 立即广播，绕开 project_change_hint 的 0.5s 轮询等待。订阅此事件可让"剧本已生成"
// 通知和项目状态刷新在同一轮 SSE 帧内完成，不再依赖 fingerprint 对比。前端收到后
// 应：1) 立即 refreshProject 拉取最新状态；2) 弹 success 通知（若 payload.episode
// 有值）；3) 可选触发到对应剧集页的 focus。
export interface ProjectScriptSavedPayload {
  project_name: string;
  script_filename: string;
  episode: number | null;
  saved_at: string;
}

export interface WorkspaceFocusTarget {
  request_id: string;
  type: "character" | "scene" | "prop" | "segment" | "grid" | "reference_unit" | "script";
  id: string;
  route: string;
  highlight: true;
  highlight_style: "flash";
  expires_at: number;
}

export interface WorkspaceFocusTargetInput {
  request_id?: string;
  type: WorkspaceFocusTarget["type"];
  id: string;
  route?: string;
  highlight?: boolean;
  highlight_style?: WorkspaceFocusTarget["highlight_style"];
  expires_at?: number;
}

export interface WorkspaceNotificationTarget {
  type: WorkspaceFocusTarget["type"];
  id: string;
  route: string;
  highlight_style?: WorkspaceFocusTarget["highlight_style"];
}

export interface WorkspaceNotification {
  id: string;
  text: string;
  tone: "info" | "success" | "error" | "warning";
  created_at: number;
  read: boolean;
  target?: WorkspaceNotificationTarget | null;
}

export interface WorkspaceNotificationInput {
  text: string;
  tone?: WorkspaceNotification["tone"];
  target?: WorkspaceNotification["target"];
  read?: boolean;
}
