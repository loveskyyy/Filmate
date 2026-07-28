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
      style={{ background: "oklch(0.04 0.002 240)" }}
    >
      {/* ============ 左侧品牌区 ============ */}
      <div
        className="relative hidden flex-col justify-between overflow-hidden lg:flex"
        style={{
          width: "52%",
          background: "oklch(0.06 0.003 240)",
          borderRight: "1px solid oklch(1 0 0 / 0.07)",
        }}
      >
        {/* 橙红光晕 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 70% 60% at 20% 60%, oklch(0.75 0.18 42 / 0.08) 0%, transparent 60%), radial-gradient(ellipse 50% 40% at 80% 20%, oklch(0.85 0.14 55 / 0.05) 0%, transparent 55%)",
          }}
        />

        {/* 网格背景 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: "linear-gradient(oklch(1 0 0 / 0.03) 1px, transparent 1px), linear-gradient(90deg, oklch(1 0 0 / 0.03) 1px, transparent 1px)",
            backgroundSize: "80px 80px",
          }}
        />

        {/* 顶部 Logo */}
        <div className="relative z-10 flex items-center gap-3 p-10">
          <div
            className="grid h-10 w-10 place-items-center"
            style={{
              background: "var(--color-accent)",
              boxShadow: "0 0 24px -4px oklch(0.75 0.18 42 / 0.50)",
            }}
          >
            <Film className="h-5 w-5" style={{ color: "oklch(0.04 0 0)" }} />
          </div>
          <span
            className="font-mono text-[14px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "var(--color-text-2)", letterSpacing: "0.18em" }}
          >
            {BRAND.name}
          </span>
        </div>

        {/* 中央大标题 */}
        <div className="relative z-10 px-10 py-12">
          {/* 装饰性大字 */}
          <div
            aria-hidden
            className="pointer-events-none mb-4 select-none font-black"
            style={{
              fontSize: 140,
              lineHeight: 0.9,
              color: "oklch(1 0 0 / 0.03)",
              letterSpacing: "-0.05em",
            }}
          >
            FILM
          </div>

          <div
            aria-hidden
            style={{
              width: 48,
              height: 3,
              background: "var(--color-accent)",
              marginBottom: 24,
            }}
          />

          <h2
            className="font-black text-text"
            style={{ fontSize: 52, lineHeight: 1.05, letterSpacing: "-0.03em" }}
          >
            智能影视
            <br />
            <span style={{ color: "var(--color-accent)" }}>创作平台</span>
          </h2>
          <p className="mt-5 max-w-[360px] text-[13px] leading-[1.8]" style={{ color: "var(--color-text-4)" }}>
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
                className="inline-flex items-center gap-1.5 rounded-none px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em]"
                style={{
                  background: "oklch(0.75 0.18 42 / 0.08)",
                  border: "1px solid oklch(0.75 0.18 42 / 0.20)",
                  color: "var(--color-accent)",
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
          <p className="font-mono text-[9px] uppercase tracking-[0.14em]" style={{ color: "var(--color-text-4)" }}>
            © {new Date().getFullYear()} {BRAND.name} · AI-Powered Film Production
          </p>
        </div>
      </div>

      {/* ============ 右侧表单区 ============ */}
      <div
        className="relative flex flex-1 flex-col items-center justify-center px-8 py-12"
        style={{
          background: "oklch(0.04 0.002 240)",
        }}
      >
        {/* 右侧背景光晕 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: "radial-gradient(ellipse 60% 40% at 50% 100%, oklch(0.75 0.18 42 / 0.04) 0%, transparent 60%)",
          }}
        />

        {/* 移动端 Logo（仅小屏显示） */}
        <div className="relative z-10 mb-8 flex items-center gap-2 lg:hidden">
          <div
            className="grid h-8 w-8 place-items-center"
            style={{
              background: "var(--color-accent)",
              boxShadow: "0 0 16px -4px oklch(0.75 0.18 42 / 0.50)",
            }}
          >
            <Film className="h-4 w-4" style={{ color: "oklch(0.04 0 0)" }} />
          </div>
          <span className="font-mono text-[13px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--color-text-2)" }}>{BRAND.name}</span>
        </div>

        {/* 表单卡片 */}
        <div
          className="relative z-10 w-full max-w-[420px] overflow-hidden"
          style={{
            background: "oklch(0.07 0.004 240)",
            border: "1px solid oklch(1 0 0 / 0.10)",
            borderTop: "3px solid var(--color-accent)",
            boxShadow: "0 32px 80px -32px oklch(0 0 0 / 0.90), 0 0 40px -20px oklch(0.75 0.18 42 / 0.10)",
          }}
        >
          <div className="p-8">
            {/* 标题区 */}
            <div className="mb-8">
              <div className="font-mono text-[9px] font-bold uppercase tracking-[0.22em] mb-3" style={{ color: "var(--color-accent)" }}>
                {isRegister ? "Create Account" : "Sign In"}
              </div>
              <h1 className="font-black text-[32px] tracking-tight text-text" style={{ letterSpacing: "-0.03em", lineHeight: 1.1 }}>
                {isRegister ? "创建账号" : "欢迎回来"}
              </h1>
              <p className="mt-2 text-[12px]" style={{ color: "var(--color-text-4)" }}>
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
                <p role="alert" aria-live="polite" className="px-3 py-2 text-[13px]" style={{ background: "oklch(0.55 0.18 30 / 0.12)", border: "1px solid oklch(0.55 0.18 30 / 0.25)", color: "var(--color-warm-bright)" }}>
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className={`${ACCENT_BTN_CLS} mt-2 w-full justify-center py-3 text-[13px] font-bold uppercase tracking-[0.08em]`}
                style={ACCENT_BUTTON_STYLE}
              >
                {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
                {loading
                  ? (isRegister ? t("auth:registering") : t("auth:logging_in"))
                  : (isRegister ? t("auth:register") : t("auth:login"))}
              </button>
            </form>

            <div className="mt-6 border-t pt-5" style={{ borderColor: "oklch(1 0 0 / 0.08)" }}>
              <button
                type="button"
                onClick={switchMode}
                className="w-full text-center text-[12px] transition-colors"
                style={{ color: "var(--color-text-4)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-text)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-text-4)")}
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
