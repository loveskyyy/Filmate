import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
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
  CARD_STYLE,
  INPUT_CLS,
  ambientGlowStyle,
  posterGridStyle,
} from "@/components/ui/darkroom-tokens";

const POSTER_GRID_STYLE = posterGridStyle({ size: 44, maskShape: "60% 60% at 50% 35%", opacity: 0.05 });
const AMBIENT_GLOW_STYLE = ambientGlowStyle();

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
        // 注册
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

        // 注册成功后自动登录
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
        // 登录
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
      className="relative flex min-h-screen items-center justify-center overflow-hidden bg-bg px-4 text-text"
    >
      <div aria-hidden className="pointer-events-none absolute inset-0" style={AMBIENT_GLOW_STYLE} />
      <div aria-hidden className="pointer-events-none absolute inset-0" style={POSTER_GRID_STYLE} />

      <div
        className="relative w-full max-w-sm overflow-hidden rounded-2xl border border-hairline p-8 shadow-2xl"
        style={CARD_STYLE}
      >
        <div className="mb-6 text-center">
          <div className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-4">
            system · {isRegister ? "register" : "login"}
          </div>
          <h1 className="font-editorial mt-1 flex items-center justify-center gap-2 text-[28px] tracking-tight text-text">
            <img src="/android-chrome-192x192.png" alt="" aria-hidden className="h-7 w-7" />
            <span>{BRAND.name}</span>
          </h1>
        </div>

        <form onSubmit={voidPromise(handleSubmit)} className="space-y-4">
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
            <p role="alert" aria-live="polite" className="text-sm text-warm-bright">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`${ACCENT_BTN_CLS} w-full justify-center`}
            style={ACCENT_BUTTON_STYLE}
          >
            {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
            {loading
              ? (isRegister ? t("auth:registering") : t("auth:logging_in"))
              : (isRegister ? t("auth:register") : t("auth:login"))}
          </button>
        </form>

        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={switchMode}
            className="text-sm text-text-4 hover:text-text transition-colors"
          >
            {isRegister ? t("auth:has_account") : t("auth:no_account")}
          </button>
        </div>
      </div>
    </div>
  );
}
