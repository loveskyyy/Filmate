import { useState, type FormEvent } from "react";
import { Loader2, Film, Clapperboard, Sparkles } from "lucide-react";
import { useAutoFocus } from "@/hooks/useAutoFocus";
import { errMsg, voidPromise } from "@/utils/async";
import { useLocation, useSearch } from "wouter";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth-store";
import { safeReturnPath } from "@/utils/safe-url";
import { BRAND } from "@/branding";
import type { LoginResponse, ErrorResponse } from "@/api";
import { FieldLabel } from "@/components/ui/FieldLabel";
import {
  ACCENT_BTN_CLS,
  ACCENT_BUTTON_STYLE,
  INPUT_CLS,
} from "@/components/ui/darkroom-tokens";

export function LoginPage() {
  const { t, i18n } = useTranslation(["common", "auth"]);
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [, setLocation] = useLocation();
  const search = useSearch();
  const login = useAuthStore((s) => s.login);
  const usernameRef = useAutoFocus<HTMLInputElement>();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isRegister) {
        if (password !== confirmPassword) {
          throw new Error(t("auth:password_mismatch"));
        }

        const resp = await fetch("/api/v1/auth/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept-Language": i18n.language || "zh",
          },
          body: JSON.stringify({
            username,
            password,
            email: email || null,
          }),
        });

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
          const detail = data.detail;
          throw new Error(typeof detail === "string" ? detail : t("auth:register_failed"));
        }

        const loginBody = new URLSearchParams({
          username,
          password,
          grant_type: "password",
        });
        const loginResp = await fetch("/api/v1/auth/token", {
          method: "POST",
          headers: {
            "Accept-Language": i18n.language || "zh",
          },
          body: loginBody,
        });

        if (!loginResp.ok) {
          throw new Error(t("auth:register_success_login_failed"));
        }

        const loginData = await loginResp.json() as LoginResponse;
        login(loginData.access_token, username);
        const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
        setLocation(returnTo ?? "/app/projects");
      } else {
        const body = new URLSearchParams({
          username,
          password,
          grant_type: "password",
        });
        const resp = await fetch("/api/v1/auth/token", {
          method: "POST",
          headers: {
            "Accept-Language": i18n.language || "zh",
          },
          body,
        });

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
          const detail = data.detail;
          throw new Error(typeof detail === "string" ? detail : t("auth:login_failed"));
        }

        const data = await resp.json() as LoginResponse;
        login(data.access_token, username);
        const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
        setLocation(returnTo ?? "/app/projects");
      }
    } catch (err) {
      setError(errMsg(err, isRegister ? t("auth:register_failed") : t("auth:login_failed")));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setIsRegister(!isRegister);
    setError("");
  };

  return (
    <div
      data-testid="login-page"
      className="relative flex min-h-screen overflow-hidden text-text"
      style={{ background: "oklch(0.07 0.006 240)" }}
    >
      {/* ============ 左侧品牌区 ============ */}
      <div
        className="relative hidden flex-col justify-between overflow-hidden lg:flex"
        style={{
          width: "55%",
          background: "linear-gradient(135deg, oklch(0.10 0.012 240) 0%, oklch(0.08 0.008 220) 100%)",
          borderRight: "1px solid oklch(0.82 0.16 200 / 0.12)",
        }}
      >
        {/* 背景光晕 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 80% 60% at 30% 40%, oklch(0.55 0.15 200 / 0.12) 0%, transparent 65%), radial-gradient(ellipse 60% 50% at 70% 80%, oklch(0.45 0.12 240 / 0.08) 0%, transparent 60%)",
          }}
        />

        {/* 网格背景 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: "linear-gradient(oklch(0.82 0.16 200 / 0.04) 1px, transparent 1px), linear-gradient(90deg, oklch(0.82 0.16 200 / 0.04) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        {/* 顶部 Logo */}
        <div className="relative z-10 flex items-center gap-3 p-10">
          <div
            className="grid h-10 w-10 place-items-center rounded-xl"
            style={{
              background: "linear-gradient(135deg, var(--color-accent), var(--color-accent-2))",
              boxShadow: "0 0 24px -4px var(--color-accent-glow)",
            }}
          >
            <Film className="h-5 w-5" style={{ color: "oklch(0.08 0 0)" }} />
          </div>
          <span
            className="font-editorial text-[22px] tracking-tight text-text"
            style={{ letterSpacing: "-0.02em" }}
          >
            {BRAND.name}
          </span>
        </div>

        {/* 中央大标题 */}
        <div className="relative z-10 px-10 py-12">
          {/* 装饰性大数字 */}
          <div
            aria-hidden
            className="font-editorial pointer-events-none mb-6 select-none"
            style={{
              fontSize: 120,
              lineHeight: 1,
              color: "oklch(0.82 0.16 200 / 0.06)",
              letterSpacing: "-0.04em",
            }}
          >
            AI
          </div>

          <h2
            className="font-editorial mb-4 text-text"
            style={{ fontSize: 48, lineHeight: 1.1, letterSpacing: "-0.02em" }}
          >
            智能影视
            <br />
            <span style={{ color: "var(--color-accent-2)", fontStyle: "italic" }}>创作平台</span>
          </h2>
          <p className="max-w-[380px] text-[14px] leading-[1.7] text-text-3">
            {BRAND.tagline ?? "从剧本到分镜，AI 全程辅助创作。让每一个创意都能高效落地。"}
          </p>

          {/* 特性标签 */}
          <div className="mt-8 flex flex-wrap gap-2">
            {[
              { icon: <Clapperboard className="h-3 w-3" />, label: "分镜生成" },
              { icon: <Sparkles className="h-3 w-3" />, label: "AI 辅助" },
              { icon: <Film className="h-3 w-3" />, label: "多集管理" },
            ].map((feat) => (
              <div
                key={feat.label}
                className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-medium"
                style={{
                  background: "oklch(0.76 0.09 200 / 0.12)",
                  border: "1px solid oklch(0.76 0.09 200 / 0.20)",
                  color: "var(--color-accent-2)",
                }}
              >
                {feat.icon}
                {feat.label}
              </div>
            ))}
          </div>
        </div>

        {/* 底部版权 */}
        <div className="relative z-10 p-10">
          <p className="font-mono text-[10px] text-text-4">
            © {new Date().getFullYear()} {BRAND.name} · AI-Powered Film Production
          </p>
        </div>
      </div>

      {/* ============ 右侧表单区 ============ */}
      <div
        className="relative flex flex-1 flex-col items-center justify-center px-8 py-12"
        style={{
          background: "oklch(0.08 0.007 240)",
        }}
      >
        {/* 右侧背景光晕 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 70% 50% at 50% 0%, oklch(0.55 0.15 200 / 0.06) 0%, transparent 60%)",
          }}
        />

        {/* 移动端 Logo（仅小屏显示） */}
        <div className="relative z-10 mb-8 flex items-center gap-2 lg:hidden">
          <div
            className="grid h-8 w-8 place-items-center rounded-lg"
            style={{
              background: "linear-gradient(135deg, var(--color-accent), var(--color-accent-2))",
              boxShadow: "0 0 16px -4px var(--color-accent-glow)",
            }}
          >
            <Film className="h-4 w-4" style={{ color: "oklch(0.08 0 0)" }} />
          </div>
          <span className="font-editorial text-[20px] tracking-tight text-text">{BRAND.name}</span>
        </div>

        {/* 表单卡片 */}
        <div
          className="relative z-10 w-full max-w-[400px] overflow-hidden rounded-2xl"
          style={{
            background: "oklch(0.11 0.010 240 / 0.90)",
            border: "1px solid oklch(0.82 0.16 200 / 0.15)",
            boxShadow: "0 32px 80px -32px oklch(0 0 0 / 0.8), 0 0 0 1px oklch(0.82 0.16 200 / 0.06)",
          }}
        >
          {/* 顶部装饰线 */}
          <div
            aria-hidden
            className="h-[2px] w-full"
            style={{
              background: "linear-gradient(90deg, transparent 0%, var(--color-accent) 40%, var(--color-accent-2) 60%, transparent 100%)",
            }}
          />

          <div className="p-8">
            {/* 标题区 */}
            <div className="mb-8">
              <div className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-4">
                {isRegister ? "Create Account" : "Sign In"}
              </div>
              <h1 className="font-editorial mt-2 text-[28px] tracking-tight text-text" style={{ letterSpacing: "-0.02em" }}>
                {isRegister ? "创建账号" : "欢迎回来"}
              </h1>
              <p className="mt-1 text-[13px] text-text-3">
                {isRegister
                  ? "注册后即可开始 AI 影视创作"
                  : "登录以继续您的创作项目"}
              </p>
            </div>

            <form onSubmit={voidPromise(handleSubmit)} className="space-y-5">
              <div>
                <FieldLabel htmlFor="login-username" required>
                  {t("auth:username")}
                </FieldLabel>
                <input
                  id="login-username"
                  type="text"
                  autoComplete="username"
                  spellCheck={false}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={INPUT_CLS}
                  ref={usernameRef}
                  required
                />
              </div>

              {isRegister && (
                <div>
                  <FieldLabel htmlFor="login-email">
                    {t("auth:email") || "邮箱"}
                  </FieldLabel>
                  <input
                    id="login-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className={INPUT_CLS}
                  />
                </div>
              )}

              <div>
                <FieldLabel htmlFor="login-password" required>
                  {t("auth:password")}
                </FieldLabel>
                <input
                  id="login-password"
                  type="password"
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={INPUT_CLS}
                  required
                />
              </div>

              {isRegister && (
                <div>
                  <FieldLabel htmlFor="login-confirm-password" required>
                    {t("auth:confirm_password")}
                  </FieldLabel>
                  <input
                    id="login-confirm-password"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className={INPUT_CLS}
                    required
                  />
                </div>
              )}

              {error && (
                <p role="alert" aria-live="polite" className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "oklch(0.55 0.18 30 / 0.12)", border: "1px solid oklch(0.55 0.18 30 / 0.25)", color: "var(--color-warm-bright)" }}>
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className={`${ACCENT_BTN_CLS} mt-2 w-full justify-center py-2.5 text-[14px]`}
                style={ACCENT_BUTTON_STYLE}
              >
                {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
                {loading
                  ? (isRegister ? t("auth:registering") : t("auth:logging_in"))
                  : (isRegister ? t("auth:register") : t("auth:login"))}
              </button>
            </form>

            <div className="mt-6 border-t pt-5" style={{ borderColor: "oklch(0.82 0.16 200 / 0.10)" }}>
              <button
                type="button"
                onClick={switchMode}
                className="w-full text-center text-[13px] text-text-4 transition-colors hover:text-text"
              >
                {isRegister ? t("auth:has_account") : t("auth:no_account")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
