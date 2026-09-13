"use client";

import Image from "next/image";
import { PointerEvent, useEffect, useRef, useState } from "react";

const actions = Array.from({ length: 6 }, (_, index) =>
  `/mascot/action-${index + 1}.gif`,
);

const messages = [
  "一起探索知识吧",
  "正在整理学习路线",
  "点击知识节点看看",
  "下一站学什么？",
  "真实资料来自知乎",
  "看山陪你慢慢学",
];

function clampPosition(x: number, y: number) {
  const compact = window.innerWidth <= 560;
  const width = compact ? 122 : 190;
  const height = compact ? 130 : 225;
  return {
    x: Math.max(0, Math.min(window.innerWidth - width, x)),
    y: Math.max(0, Math.min(window.innerHeight - height, y)),
  };
}

export function KanshanPet() {
  const [actionIndex, setActionIndex] = useState(0);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [drag, setDrag] = useState<{ pointerX: number; pointerY: number; startX: number; startY: number } | null>(null);
  const didDrag = useRef(false);
  const latestPosition = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("kanshan-pet-position") ?? "null") as { x?: unknown; y?: unknown } | null;
      if (saved && typeof saved.x === "number" && typeof saved.y === "number") {
        const restored = clampPosition(saved.x, saved.y);
        latestPosition.current = restored;
        setPosition(restored);
      }
    } catch {
      localStorage.removeItem("kanshan-pet-position");
    }

    const keepInsideViewport = () => setPosition((current) => {
      if (!current) return current;
      const next = clampPosition(current.x, current.y);
      latestPosition.current = next;
      return next;
    });
    window.addEventListener("resize", keepInsideViewport);
    return () => window.removeEventListener("resize", keepInsideViewport);
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    function scheduleNextAction() {
      // Each action stays visible for 5–6 seconds. Picking a non-zero offset
      // guarantees that the same animation is not selected twice in a row.
      timer = setTimeout(() => {
        setActionIndex((current) => {
          const offset = 1 + Math.floor(Math.random() * (actions.length - 1));
          return (current + offset) % actions.length;
        });
        scheduleNextAction();
      }, 5000 + Math.random() * 1000);
    }

    scheduleNextAction();
    return () => clearTimeout(timer);
  }, []);

  function startDrag(event: PointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const container = event.currentTarget.closest(".kanshan-pet");
    const rect = container?.getBoundingClientRect();
    const start = position ?? { x: rect?.left ?? 0, y: rect?.top ?? 0 };
    latestPosition.current = start;
    setPosition(start);
    setDrag({ pointerX: event.clientX, pointerY: event.clientY, startX: start.x, startY: start.y });
    didDrag.current = false;
  }

  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!drag) return;
    const dx = event.clientX - drag.pointerX;
    const dy = event.clientY - drag.pointerY;
    if (Math.abs(dx) + Math.abs(dy) > 4) didDrag.current = true;
    const next = clampPosition(drag.startX + dx, drag.startY + dy);
    latestPosition.current = next;
    setPosition(next);
  }

  function finishDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!drag) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDrag(null);
    if (latestPosition.current) {
      localStorage.setItem("kanshan-pet-position", JSON.stringify(latestPosition.current));
    }
  }

  return (
    <aside
      className={`kanshan-pet${drag ? " is-pet-dragging" : ""}`}
      aria-label="看山桌宠"
      style={position ? { left: position.x, top: position.y, right: "auto", bottom: "auto" } : undefined}
    >
      <div className="pet-message">{messages[actionIndex]}</div>
      <button
        className="pet-stage"
        type="button"
        title="拖动看山到任意位置，点击可切换动作"
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onClick={() => {
          if (didDrag.current) {
            didDrag.current = false;
            return;
          }
          setActionIndex((current) => (current + 1) % actions.length);
        }}
      >
        <Image
          key={actions[actionIndex]}
          src={actions[actionIndex]}
          alt="正在活动的看山吉祥物"
          width={320}
          height={320}
          unoptimized
          priority
          draggable={false}
        />
      </button>
      <span className="pet-shadow" aria-hidden="true" />
    </aside>
  );
}
