import { useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  LayoutDashboard,
  BookOpen,
  Users,
  Landmark,
  Package,
  Plus,
  Search,
  ShoppingBag,
} from "lucide-react";
import { useProjectsStore } from "@/stores/projects-store";
import { useCostStore } from "@/stores/cost-store";
import { useAppStore } from "@/stores/app-store";
import { API } from "@/api";
import { EpisodeCard } from "./EpisodeCard";

interface AssetSidebarProps {
  className?: string;
}

interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  meta?: number;
}

/**
 * 工作台侧栏 v4：
 * - 加宽至 280px（折叠 68px）
 * - 导航项更大，图标更醒目
 * - 分组标题更具电影感
 */
export function AssetSidebar({ className }: AssetSidebarProps) {
  const { t } = useTranslation(["common", "dashboard"]);
  const { currentProjectName, currentProjectData } = useProjectsStore();
  const debouncedFetchCost = useCostStore((s) => s.debouncedFetch);
  const [location, setLocation] = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState("");

  const characterCount = Object.keys(currentProjectData?.characters ?? {}).length;
  const sceneCount = Object.keys(currentProjectData?.scenes ?? {}).length;
  const propCount = Object.keys(currentProjectData?.props ?? {}).length;
  const productCount = Object.keys(currentProjectData?.products ?? {}).length;
  const episodes = currentProjectData?.episodes ?? [];
  const isAd = currentProjectData?.content_mode === "ad";

  const sourceFilesVersion = useAppStore((s) => s.sourceFilesVersion);
  const [sourceCount, setSourceCount] = useState<number>(0);

  useEffect(() => {
    if (currentProjectName) debouncedFetchCost(currentProjectName);
  }, [currentProjectName, debouncedFetchCost]);

  useEffect(() => {
    if (!currentProjectName) return;
    let cancelled = false;
    API.listFiles(currentProjectName)
      .then((res) => {
        if (!cancelled) setSourceCount(res.files?.source?.length ?? 0);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentProjectName, sourceFilesVersion]);

  const activeEp = useMemo(() => {
    const m = location.match(/^\/episodes\/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }, [location]);

  const navItems: NavItem[] = [
    { key: "overview", path: "/", label: t("dashboard:workspace_nav_overview"), icon: LayoutDashboard },
    {
      key: "source",
      path: "/source",
      label: t("dashboard:workspace_nav_source"),
      icon: BookOpen,
      meta: sourceCount,
    },
    {
      key: "characters",
      path: "/characters",
      label: t("dashboard:workspace_nav_characters"),
      icon: Users,
      meta: characterCount,
    },
    {
      key: "scenes",
      path: "/scenes",
      label: t("dashboard:workspace_nav_scenes"),
      icon: Landmark,
      meta: sceneCount,
    },
    {
      key: "props",
      path: "/props",
      label: t("dashboard:workspace_nav_props"),
      icon: Package,
      meta: propCount,
    },
    ...(isAd
      ? [
          {
            key: "products",
            path: "/products",
            label: t("dashboard:workspace_nav_products"),
            icon: ShoppingBag,
            meta: productCount,
          },
        ]
      : []),
  ];

  const isNavActive = (item: NavItem): boolean => {
    if (item.path === "/") return location === "/";
    return location === item.path || location.startsWith(item.path + "/");
  };

  const filteredEps = isAd
    ? episodes
    : episodes.filter(
        (ep) => !search || ep.title.includes(search) || String(ep.episode).includes(search),
      );

  return (
    <aside
      className={`flex flex-col overflow-hidden ${className ?? ""}`}
      style={{
        width: collapsed ? 68 : 280,
        transition: "width .20s ease",
        borderRight: "1px solid oklch(1 0 0 / 0.08)",
        background: "oklch(0.05 0.003 240 / 0.98)",
        boxShadow: "inset -1px 0 0 oklch(1 0 0 / 0.04), 6px 0 32px -12px oklch(0 0 0 / 0.5)",
      }}
    >
      {/* ---- 分组标题：WORKSPACE ---- */}
      {!collapsed && (
        <div
          className="px-4 pt-4 pb-2"
          style={{ borderBottom: "1px solid oklch(1 0 0 / 0.06)" }}
        >
          <span
            className="font-mono text-[9.5px] font-bold uppercase"
            style={{ color: "oklch(0.45 0.010 240)", letterSpacing: "0.18em" }}
          >
            Workspace
          </span>
        </div>
      )}

      {/* ---- Workspace nav ---- */}
      <div className={collapsed ? "px-2 py-3" : "px-2.5 py-2"}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isNavActive(item);
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setLocation(item.path)}
              title={collapsed ? item.label : ""}
              aria-label={collapsed ? item.label : undefined}
              className="relative mb-0.5 flex w-full items-center gap-3 rounded-lg transition-colors focus-ring"
              style={{
                padding: collapsed ? "10px 0" : "9px 10px",
                justifyContent: collapsed ? "center" : undefined,
                background: active
                  ? "linear-gradient(90deg, oklch(0.75 0.18 42 / 0.15), oklch(0.75 0.18 42 / 0.06) 70%, transparent)"
                  : "transparent",
                color: active ? "var(--color-text)" : "var(--color-text-2)",
              }}
              onMouseEnter={(e) => {
                if (!active) (e.currentTarget as HTMLElement).style.background = "oklch(1 0 0 / 0.04)";
              }}
              onMouseLeave={(e) => {
                if (!active) (e.currentTarget as HTMLElement).style.background = "transparent";
              }}
            >
              {active && (
                <span
                  className="absolute left-0 top-[8px] bottom-[8px] w-[3px] rounded-r"
                  style={{
                    background: "var(--color-accent)",
                    boxShadow: "0 0 10px var(--color-accent-glow)",
                  }}
                />
              )}
              <span
                className="grid shrink-0 place-items-center rounded-md"
                style={{
                  width: 30,
                  height: 30,
                  background: active
                    ? "oklch(0.75 0.18 42 / 0.18)"
                    : "oklch(0.09 0.004 240 / 0.60)",
                  border: active
                    ? "1px solid oklch(0.75 0.18 42 / 0.30)"
                    : "1px solid oklch(1 0 0 / 0.06)",
                  color: active ? "var(--color-accent-2)" : "var(--color-text-3)",
                }}
              >
                <Icon className="h-[15px] w-[15px]" />
              </span>
              {!collapsed && (
                <>
                  <span
                    className="flex-1 text-left text-[13px]"
                    style={{
                      fontWeight: active ? 600 : 400,
                      letterSpacing: active ? "-0.01em" : "0",
                    }}
                  >
                    {item.label}
                  </span>
                  {item.meta != null && (
                    <span
                      className="num rounded-[4px] px-1.5 py-0.5 text-[10px] font-semibold"
                      style={{
                        color: active ? "var(--color-accent-2)" : "var(--color-text-4)",
                        background: active
                          ? "oklch(0.75 0.18 42 / 0.12)"
                          : "oklch(0.09 0.004 240 / 0.60)",
                        border: "1px solid oklch(1 0 0 / 0.07)",
                      }}
                    >
                      {item.meta}
                    </span>
                  )}
                </>
              )}
            </button>
          );
        })}
      </div>

      {/* ---- 分隔线 ---- */}
      <div
        className="mx-3 my-1 h-px"
        style={{ background: "oklch(1 0 0 / 0.07)" }}
      />

      {/* ---- Episodes ---- */}
      {!collapsed ? (
        <>
          {/* 分组标题：EPISODES */}
          <div className="flex items-center gap-2 px-4 pt-3 pb-2">
            <span
              className="font-mono text-[9.5px] font-bold uppercase"
              style={{ color: "oklch(0.45 0.010 240)", letterSpacing: "0.18em" }}
            >
              {isAd
                ? t("dashboard:ad_video_section_title")
                : t("dashboard:episodes_section_title")}
            </span>
            {!isAd && (
              <>
                <span
                  className="num rounded-[3px] px-1 py-px text-[9.5px] font-semibold"
                  style={{
                    color: "var(--color-text-4)",
                    background: "oklch(0.09 0.004 240 / 0.60)",
                    border: "1px solid oklch(1 0 0 / 0.06)",
                  }}
                >
                  {episodes.length}
                </span>
                <span className="flex-1" />
                <button
                  type="button"
                  disabled
                  aria-disabled="true"
                  className="grid h-6 w-6 place-items-center rounded-md focus-ring disabled:cursor-not-allowed disabled:opacity-40"
                  style={{
                    background: "oklch(0.18 0.012 242 / 0.60)",
                    border: "1px solid oklch(1 0 0 / 0.08)",
                    color: "var(--color-text-3)",
                  }}
                  title={t("dashboard:add_episode_unavailable")}
                  aria-label={t("dashboard:add_episode")}
                >
                  <Plus className="h-3 w-3" />
                </button>
              </>
            )}
          </div>

          {!isAd && (
            <div className="px-2.5 pb-2">
              <div
                className="flex items-center gap-2 rounded-lg px-3 py-2"
                style={{
                  background: "oklch(0.13 0.010 240 / 0.70)",
                  border: "1px solid oklch(1 0 0 / 0.07)",
                }}
              >
                <Search
                  className="h-3 w-3 shrink-0"
                  style={{ color: "var(--color-text-4)" }}
                />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("dashboard:episode_search_placeholder")}
                  aria-label={t("dashboard:episode_search_placeholder")}
                  className="min-w-0 flex-1 bg-transparent text-[12px] outline-none focus-ring"
                  style={{ color: "var(--color-text)" }}
                />
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-2 pb-3">
            {filteredEps.length === 0 ? (
              <div
                className="px-2 py-8 text-center text-[11px] italic"
                style={{ color: "var(--color-text-4)" }}
              >
                {episodes.length === 0
                  ? t("dashboard:no_episodes_yet")
                  : t("dashboard:no_episode_search_results")}
              </div>
            ) : (
              filteredEps.map((ep) => (
                <EpisodeCard
                  key={ep.episode}
                  ep={ep}
                  active={ep.episode === activeEp}
                  onClick={() => setLocation(`/episodes/${ep.episode}`)}
                  showEpisodeBadge={!isAd}
                  fallbackTitle={isAd ? currentProjectData?.title : undefined}
                />
              ))
            )}
          </div>
        </>
      ) : (
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {filteredEps.map((ep) => {
            const epLabel = isAd
              ? t("dashboard:ad_video_section_title")
              : t("dashboard:episode_collapsed_button_label", {
                  episode: ep.episode,
                  title: ep.title,
                });
            return (
              <button
                key={ep.episode}
                type="button"
                onClick={() => setLocation(`/episodes/${ep.episode}`)}
                title={epLabel}
                aria-label={epLabel}
                className="num mb-1 flex h-10 w-full items-center justify-center rounded-lg text-[11px] font-bold focus-ring transition-colors"
                style={{
                  background: ep.episode === activeEp
                    ? "oklch(0.75 0.18 42 / 0.18)"
                    : "oklch(0.14 0.010 240 / 0.50)",
                  border: ep.episode === activeEp
                    ? "1px solid oklch(0.75 0.18 42 / 0.25)"
                    : "1px solid oklch(1 0 0 / 0.06)",
                  color: ep.episode === activeEp
                    ? "var(--color-accent-2)"
                    : "var(--color-text-3)",
                }}
              >
                {isAd ? <Clapperboard className="h-4 w-4" aria-hidden /> : `E${ep.episode}`}
              </button>
            );
          })}
        </div>
      )}

      {/* ---- Collapse footer ---- */}
      <div
        className="flex items-center gap-2 px-2.5 py-2.5"
        style={{
          borderTop: "1px solid oklch(1 0 0 / 0.07)",
          background: "oklch(0.04 0.002 240 / 0.95)",
        }}
      >
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="grid h-8 w-8 place-items-center rounded-lg focus-ring transition-colors"
          aria-expanded={!collapsed}
          style={{
            background: "oklch(0.18 0.012 242 / 0.60)",
            border: "1px solid oklch(1 0 0 / 0.08)",
            color: "var(--color-text-3)",
          }}
          title={collapsed ? t("dashboard:sidebar_expand") : t("dashboard:sidebar_collapse")}
          aria-label={
            collapsed ? t("dashboard:sidebar_expand") : t("dashboard:sidebar_collapse")
          }
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
    </aside>
  );
}
