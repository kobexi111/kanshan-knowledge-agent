"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { KanshanPet } from "@/components/KanshanPet";
import { KnowledgeGraph } from "@/components/KnowledgeGraph";
import {
  loadPersonalization,
  recommendations,
  recordView,
  rememberRecommendations,
  type BrowsingItem,
  type PersonalizationData,
  type RecommendationItem,
} from "@/lib/personalization";
import type {
  LearningRouteResponse,
  RouteStageName,
  RouteStep,
  RouteStreamEvent,
} from "@/types/route";

interface AuthSessionResponse {
  authenticated: boolean;
  configured: boolean;
  provider: "zhihu" | null;
  profile_id: string | null;
}

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const stageLabels = {
  prerequisite: "前置知识",
  current: "当前知识",
  advanced: "进阶知识",
} as const;

type StageStatus = "pending" | "running" | "done";

const initialStageStatuses: Record<RouteStageName, StageStatus> = {
  prerequisite: "pending",
  current: "pending",
  advanced: "pending",
};

function RouteSection({
  name,
  steps,
  status = "done",
  onMaterialOpen,
}: {
  name: RouteStageName;
  steps: RouteStep[];
  status?: StageStatus;
  onMaterialOpen: (item: Omit<BrowsingItem, "viewedAt" | "visits">) => void;
}) {
  return (
    <section className={`route-section route-${name}`}>
      <h2>{stageLabels[name]}</h2>
      {steps.length === 0 && (
        <div className={`route-placeholder is-${status}`} aria-live="polite">
          {status === "running" ? "正在生成这一阶段…" : "等待上一阶段完成"}
        </div>
      )}
      {steps.map((step) => (
        <article className="route-card" key={step.title}>
          <div className="card-heading">
            <h3>{step.title}</h3>
            <span>{step.difficulty}</span>
          </div>
          <p>{step.description}</p>
          <ul>
            {step.materials.map((material) => (
              <li key={material.title}>
                {material.url ? (
                  <a
                    href={material.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => onMaterialOpen({
                      url: material.url!,
                      title: material.title,
                      topic: step.title,
                      reason: material.reason,
                      stage: name,
                    })}
                  >
                    {material.title}
                  </a>
                ) : (
                  <strong>{material.title}</strong>
                )}
                {material.is_mock && <em>Mock</em>}
                <small>{material.reason}</small>
              </li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
}

export default function Home() {
  const [auth, setAuth] = useState<AuthSessionResponse | null>(null);
  const [authNotice, setAuthNotice] = useState("");
  const [url, setUrl] = useState("");
  const [route, setRoute] = useState<LearningRouteResponse | null>(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [view, setView] = useState<"route" | "graph">("route");
  const [stageStatuses, setStageStatuses] =
    useState<Record<RouteStageName, StageStatus>>(initialStageStatuses);
  const [personalization, setPersonalization] = useState<PersonalizationData>({ history: [], candidates: [] });
  const routeRef = useRef<LearningRouteResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkSession() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/auth/session`, {
          cache: "no-store",
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Session check failed");
        const session = (await response.json()) as AuthSessionResponse;
        if (!session.authenticated) {
          window.location.replace("/login");
          return;
        }
        setAuth(session);
        if (session.profile_id) setPersonalization(loadPersonalization(session.profile_id));
      } catch (requestError) {
        if (requestError instanceof Error && requestError.name === "AbortError") return;
        window.location.replace("/login?service=unavailable");
      }
    }

    const oauthResult = new URLSearchParams(window.location.search).get("oauth");
    if (oauthResult === "success") setAuthNotice("知乎授权成功");
    if (oauthResult) window.history.replaceState({}, "", window.location.pathname);

    void checkSession();
    return () => controller.abort();
  }, []);

  function logout() {
    window.location.assign(`${apiBaseUrl}/api/auth/logout`);
  }

  function switchAccount() {
    window.location.assign(`${apiBaseUrl}/api/auth/zhihu/switch`);
  }

  function trackView(item: Omit<BrowsingItem, "viewedAt" | "visits">) {
    if (!auth?.profile_id) return;
    setPersonalization(recordView(auth.profile_id, item));
  }

  function openRecommendation(item: RecommendationItem) {
    trackView({
      url: item.url,
      title: item.title,
      topic: item.topic,
      reason: item.reason,
      stage: item.stage,
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setRoute(null);
    routeRef.current = null;
    setIsSubmitting(true);
    setView("route");
    setStageStatuses({
      prerequisite: "running",
      current: "pending",
      advanced: "pending",
    });

    try {
      const response = await fetch(`${apiBaseUrl}/api/routes/generate/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        const responseBody = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(
          response.status === 422
            ? "请输入有效的知乎链接，例如 https://www.zhihu.com/question/123456"
            : responseBody?.detail ?? "生成失败，请确认后端正在运行。",
        );
      }

      if (!response.body) throw new Error("浏览器无法读取流式响应。");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function applyEvent(streamEvent: RouteStreamEvent) {
        if (streamEvent.type === "error") throw new Error(streamEvent.message);
        if (streamEvent.type === "progress") {
          setStageStatuses((previous) => ({
            ...previous,
            [streamEvent.stage]: "running",
          }));
          return;
        }
        if (streamEvent.type === "source") {
          const nextRoute: LearningRouteResponse = {
            source: streamEvent.source,
            route: { prerequisite: [], current: [], advanced: [] },
            notice: streamEvent.notice,
          };
          routeRef.current = nextRoute;
          setRoute(nextRoute);
          return;
        }
        if (streamEvent.type === "stage") {
          if (routeRef.current) {
            const nextRoute = {
              ...routeRef.current,
              route: { ...routeRef.current.route, [streamEvent.stage]: streamEvent.steps },
            };
            routeRef.current = nextRoute;
            setRoute(nextRoute);
          }
          setStageStatuses((previous) => ({
            ...previous,
            [streamEvent.stage]: "done",
          }));
          return;
        }
        if (streamEvent.type === "recommendations" && auth?.profile_id) {
          setPersonalization(rememberRecommendations(auth.profile_id, streamEvent.items));
        }
      }

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.trim()) applyEvent(JSON.parse(line) as RouteStreamEvent);
        }
        if (done) break;
      }
      if (buffer.trim()) applyEvent(JSON.parse(buffer) as RouteStreamEvent);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "生成失败，请稍后重试。",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!auth?.authenticated) {
    return (
      <main className="auth-loading" aria-live="polite">
        <span />
        正在验证登录状态…
      </main>
    );
  }

  return (
    <main>
      <div className="page-shell">
        <section className="hero" aria-labelledby="page-title">
          <div className="hero-topbar">
            <div className="auth-actions">
              <span className="auth-state">知乎已授权</span>
              <button type="button" className="auth-button secondary" onClick={switchAccount}>
                切换账号
              </button>
              <button type="button" className="auth-button secondary" onClick={logout}>
                退出登录
              </button>
            </div>
          </div>

          {authNotice && <p className="auth-notice" role="status">{authNotice}</p>}

          <h1 id="page-title">看山知识导航</h1>
          <p className="subtitle">把一篇知乎内容转换成渐进式学习路线</p>

          <form onSubmit={handleSubmit}>
            <label htmlFor="zhihu-url">知乎内容链接</label>
            <div className="input-row">
              <input
                id="zhihu-url"
                name="url"
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="粘贴知乎文章 / 回答 / 问题链接"
                required
              />
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "生成中..." : "生成学习路线"}
              </button>
            </div>
            <p className="stage-note">
              当前支持知乎问题和回答链接，推荐资料来自知乎开放平台。
            </p>
          </form>

          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}

          {isSubmitting && (
            <div className="generation-progress" aria-live="polite">
              {(Object.keys(stageLabels) as RouteStageName[]).map((stage) => (
                <div className={`progress-step is-${stageStatuses[stage]}`} key={stage}>
                  <span aria-hidden="true" />
                  <strong>{stageLabels[stage]}</strong>
                  <small>
                    {stageStatuses[stage] === "done"
                      ? "已完成"
                      : stageStatuses[stage] === "running"
                        ? "生成中"
                        : "等待中"}
                  </small>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="personal-section" aria-labelledby="personal-title">
            <div className="personal-heading">
              <div>
                <p className="eyebrow">为你推荐</p>
                <h2 id="personal-title">沿着最近兴趣继续探索</h2>
              </div>
            </div>

            {recommendations(personalization).length > 0 && (
              <div className="recommendation-grid">
                {recommendations(personalization).map((item) => (
                  <a key={item.url} href={item.url} target="_blank" rel="noreferrer" onClick={() => openRecommendation(item)}>
                    <small>{item.stage === "related" ? "相关内容" : stageLabels[item.stage]} · {item.topic}</small>
                    <strong>{item.title}</strong>
                  </a>
                ))}
              </div>
            )}
            {recommendations(personalization).length === 0 && (
              <div className="personal-empty">
                <strong>暂无个性化推荐</strong>
                <span>生成一条学习路线后，这里会出现路线之外的相关知乎内容。</span>
              </div>
            )}

            {personalization.history.length > 0 && (
              <div className="recent-history">
                <h3>最近浏览</h3>
                <div>
                  {personalization.history.slice(0, 6).map((item) => (
                    <a key={item.url} href={item.url} target="_blank" rel="noreferrer" onClick={() => trackView(item)}>
                      <span>{item.title}</span>
                      <small>{item.visits > 1 ? `浏览 ${item.visits} 次` : item.topic}</small>
                    </a>
                  ))}
                </div>
              </div>
            )}
            {personalization.history.length === 0 && (
              <div className="recent-history">
                <h3>最近浏览</h3>
                <div className="personal-empty compact">
                  <strong>暂无浏览记录</strong>
                  <span>打开知乎原文或资料后，会自动记录在这里。</span>
                </div>
              </div>
            )}
          </section>

        {route && (
          <section className="results" aria-labelledby="route-title">
            <div className="source-summary">
              <p className="eyebrow">分析对象</p>
              <h2 id="route-title">{route.source.title}</h2>
              <p>{route.source.summary}</p>
              <a
                href={route.source.url}
                target="_blank"
                rel="noreferrer"
                onClick={() => trackView({
                  url: route.source.url,
                  title: route.source.title,
                  topic: route.source.title,
                  reason: "用于生成当前学习路线的知乎内容",
                  stage: "source",
                })}
              >
                查看提交的知乎链接
              </a>
            </div>

            <p className="mock-notice">{route.notice}</p>

            {!isSubmitting && <div className="view-switch" role="group" aria-label="学习路线展示方式">
              <button
                type="button"
                className={view === "route" ? "is-active" : ""}
                onClick={() => setView("route")}
              >
                三段式路线
              </button>
              <button
                type="button"
                className={view === "graph" ? "is-active" : ""}
                onClick={() => setView("graph")}
              >
                3D星图
              </button>
            </div>}

            {view === "route" ? (
              <div className="route-flow">
                <RouteSection name="prerequisite" steps={route.route.prerequisite} status={stageStatuses.prerequisite} onMaterialOpen={trackView} />
                <div className="route-arrow" aria-hidden="true">↓</div>
                <RouteSection name="current" steps={route.route.current} status={stageStatuses.current} onMaterialOpen={trackView} />
                <div className="route-arrow" aria-hidden="true">↓</div>
                <RouteSection name="advanced" steps={route.route.advanced} status={stageStatuses.advanced} onMaterialOpen={trackView} />
              </div>
            ) : (
              <KnowledgeGraph
                prerequisite={route.route.prerequisite}
                current={route.route.current}
                advanced={route.route.advanced}
              />
            )}
          </section>
        )}
      </div>
      <KanshanPet />
    </main>
  );
}
