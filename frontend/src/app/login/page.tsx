"use client";

import { useEffect, useState } from "react";

interface AuthSessionResponse {
  authenticated: boolean;
  configured: boolean;
  provider: "zhihu" | null;
}

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const [checking, setChecking] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const parameters = new URLSearchParams(window.location.search);

    if (parameters.get("oauth") === "error") {
      setMessage("知乎授权失败，请检查回调地址后重新授权。");
    } else if (parameters.get("logout") === "success") {
      setMessage("你已安全退出登录。");
    } else if (parameters.get("service") === "unavailable") {
      setMessage("暂时无法连接登录服务，请稍后重试。");
    }

    async function checkSession() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/auth/session`, {
          cache: "no-store",
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Session check failed");
        const session = (await response.json()) as AuthSessionResponse;
        setConfigured(session.configured);
        setAuthenticated(session.authenticated);
        if (session.authenticated) {
          setMessage("这个浏览器中存在已授权会话，请确认是否由本人继续使用。");
        }
      } catch (requestError) {
        if (requestError instanceof Error && requestError.name === "AbortError") return;
        setConfigured(false);
        setMessage("暂时无法连接登录服务，请稍后重试。");
      } finally {
        setChecking(false);
      }
    }

    void checkSession();
    return () => controller.abort();
  }, []);

  function loginWithZhihu() {
    window.location.assign(`${apiBaseUrl}/api/auth/zhihu/login`);
  }

  function switchAccount() {
    window.location.assign(`${apiBaseUrl}/api/auth/zhihu/switch`);
  }

  function continueToApp() {
    window.location.assign("/");
  }

  return (
    <main className="login-page">
      <section className="login-action-panel" aria-labelledby="login-title">
        <h1 id="login-title" className="visually-hidden">登录看山知识导航</h1>
        {message && <p className="login-message" role="status">{message}</p>}
        {authenticated ? (
          <div className="existing-session-actions">
            <button type="button" className="zhihu-login-button" onClick={continueToApp}>
              继续进入
            </button>
            <button type="button" className="switch-login-button" onClick={switchAccount}>
              切换其他知乎账号
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="zhihu-login-button"
            onClick={loginWithZhihu}
            disabled={checking || !configured}
          >
            {checking
              ? "正在检查登录状态…"
              : configured
                ? "使用知乎账号授权登录"
                : "登录服务暂不可用"}
          </button>
        )}
        <p className="login-privacy">安全授权 · 凭证仅由后端加密保存</p>
      </section>
    </main>
  );
}
