"use client";

import { FormEvent, useEffect, useState } from "react";

import { KanshanPet } from "@/components/KanshanPet";
import { KnowledgeGraph } from "@/components/KnowledgeGraph";
import type { LearningRouteResponse, RouteStep } from "@/types/route";

type ConnectionState = "checking" | "connected" | "disconnected";

interface HealthResponse {
  status: "ok";
  service: string;
}

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const stageLabels = {
  prerequisite: "前置知识",
  current: "当前知识",
  advanced: "进阶知识",
} as const;

function RouteSection({
  name,
  steps,
}: {
  name: keyof typeof stageLabels;
  steps: RouteStep[];
}) {
  return (
    <section className={`route-section route-${name}`}>
      <h2>{stageLabels[name]}</h2>
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
                  <a href={material.url} target="_blank" rel="noreferrer">
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
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [url, setUrl] = useState("");
  const [route, setRoute] = useState<LearningRouteResponse | null>(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [view, setView] = useState<"route" | "graph">("route");

  useEffect(() => {
    const controller = new AbortController();

    async function checkBackend() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Health check failed");

        const data = (await response.json()) as HealthResponse;
        setConnection(
          data.status === "ok" && data.service === "zhihu-knowledge-agent"
            ? "connected"
            : "disconnected",
        );
      } catch (requestError) {
        if (requestError instanceof Error && requestError.name === "AbortError") {
          return;
        }
        setConnection("disconnected");
      }
    }

    void checkBackend();
    return () => controller.abort();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setRoute(null);
    setIsSubmitting(true);

    try {
      const response = await fetch(`${apiBaseUrl}/api/routes/generate`, {
        method: "POST",
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

      setRoute((await response.json()) as LearningRouteResponse);
      setView("route");
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

  const connectionLabel = {
    checking: "Checking backend...",
    connected: "Backend connected",
    disconnected: "Backend disconnected",
  }[connection];

  return (
    <main>
      <div className="page-shell">
        <section className="hero" aria-labelledby="page-title">
          <p className={`status status-${connection}`} aria-live="polite">
            <span aria-hidden="true" />
            {connectionLabel}
          </p>

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
        </section>

        {route && (
          <section className="results" aria-labelledby="route-title">
            <div className="source-summary">
              <p className="eyebrow">分析对象</p>
              <h2 id="route-title">{route.source.title}</h2>
              <p>{route.source.summary}</p>
              <a href={route.source.url} target="_blank" rel="noreferrer">
                查看提交的知乎链接
              </a>
            </div>

            <p className="mock-notice">{route.notice}</p>

            <div className="view-switch" role="group" aria-label="学习路线展示方式">
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
            </div>

            {view === "route" ? (
              <div className="route-flow">
                <RouteSection name="prerequisite" steps={route.route.prerequisite} />
                <div className="route-arrow" aria-hidden="true">↓</div>
                <RouteSection name="current" steps={route.route.current} />
                <div className="route-arrow" aria-hidden="true">↓</div>
                <RouteSection name="advanced" steps={route.route.advanced} />
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
