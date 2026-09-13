"use client";

import { PointerEvent, WheelEvent, useMemo, useState } from "react";
import type { LearningMaterial, RouteStep } from "@/types/route";

type Stage = "prerequisite" | "current" | "advanced";
type NodeKind = "center" | "topic" | "material";
interface GraphNode { id: string; stage: Stage; kind: NodeKind; title: string; description: string; difficulty: RouteStep["difficulty"]; materials: LearningMaterial[]; material?: LearningMaterial; x: number; y: number; z: number; }
interface GraphEdge { id: string; from: GraphNode; to: GraphNode; }

const stageName: Record<Stage, string> = { prerequisite: "前置知识", current: "当前知识", advanced: "进阶知识" };
const polar = (radius: number, degrees: number) => {
  const radians = degrees * Math.PI / 180;
  return { x: Math.cos(radians) * radius, y: Math.sin(radians) * radius };
};
const spreadAngles = (count: number, from: number, to: number) => count <= 1
  ? [(from + to) / 2]
  : Array.from({ length: count }, (_, index) => from + (to - from) * index / (count - 1));

function buildBranch(steps: RouteStep[], stage: "prerequisite" | "advanced", angles: number[]) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  steps.forEach((step, stepIndex) => {
    const angle = angles[stepIndex] ?? 0;
    const point = polar(225, angle);
    const topic: GraphNode = {
      id: `${stage}-topic-${stepIndex}`, stage, kind: "topic", title: step.title,
      description: step.description, difficulty: step.difficulty, materials: step.materials,
      x: point.x, y: point.y,
      z: (stepIndex - (steps.length - 1) / 2) * 105,
    };
    nodes.push(topic);
    step.materials.forEach((material, materialIndex) => {
      const leafAngle = angle + (materialIndex - (step.materials.length - 1) / 2) * 21;
      const offset = polar(148, leafAngle);
      const leaf: GraphNode = {
        id: `${topic.id}-material-${materialIndex}`, stage, kind: "material",
        title: material.title, description: material.reason, difficulty: step.difficulty,
        materials: [material], material, x: topic.x + offset.x, y: topic.y + offset.y,
        z: topic.z + (materialIndex - (step.materials.length - 1) / 2) * 82,
      };
      nodes.push(leaf);
      edges.push({ id: `${topic.id}-${leaf.id}`, from: topic, to: leaf });
    });
  });
  return { nodes, edges };
}

function edgeStyle(edge: GraphEdge) {
  const dx = edge.to.x - edge.from.x;
  const dy = edge.to.y - edge.from.y;
  const dz = edge.to.z - edge.from.z;
  const centerDistance = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const nodeRadius = (kind: NodeKind) => kind === "center" ? 58 : kind === "topic" ? 44 : 29;
  const startRadius = nodeRadius(edge.from.kind);
  const endRadius = nodeRadius(edge.to.kind);
  const unitX = dx / centerDistance;
  const unitY = dy / centerDistance;
  const unitZ = dz / centerDistance;
  const startX = edge.from.x + unitX * startRadius;
  const startY = edge.from.y + unitY * startRadius;
  const startZ = edge.from.z + unitZ * startRadius;
  const width = Math.max(0, centerDistance - startRadius - endRadius);
  const angleZ = Math.atan2(dy, dx) * 180 / Math.PI;
  const angleY = -Math.asin(dz / centerDistance) * 180 / Math.PI;
  return { width, transform: `translate3d(${startX}px, ${startY}px, ${startZ}px) rotateZ(${angleZ}deg) rotateY(${angleY}deg)` };
}

export function KnowledgeGraph({ prerequisite, current, advanced }: {
  prerequisite: RouteStep[]; current: RouteStep[]; advanced: RouteStep[];
}) {
  const { nodes, edges } = useMemo(() => {
    const currentStep = current[0];
    if (!currentStep) return { nodes: [], edges: [] };
    const center: GraphNode = {
      id: "current-center", stage: "current", kind: "center",
      title: currentStep.title.replace(/^当前知识：/, ""), description: currentStep.description,
      difficulty: currentStep.difficulty, materials: currentStep.materials, x: 0, y: 0, z: 0,
    };
    const before = buildBranch(prerequisite, "prerequisite", spreadAngles(prerequisite.length, 135, 225));
    const after = buildBranch(advanced, "advanced", spreadAngles(advanced.length, -45, 45));
    const topics = [...before.nodes, ...after.nodes].filter((node) => node.kind === "topic");
    return {
      nodes: [center, ...before.nodes, ...after.nodes],
      edges: [
        ...topics.map((topic) => ({ id: `center-${topic.id}`, from: center, to: topic })),
        ...before.edges, ...after.edges,
      ],
    };
  }, [prerequisite, current, advanced]);

  const [selectedId, setSelectedId] = useState("current-center");
  const [rotation, setRotation] = useState({ x: -5, y: -7 });
  const [zoom, setZoom] = useState(.82);
  const [drag, setDrag] = useState<{ x: number; y: number; rotationX: number; rotationY: number } | null>(null);
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];

  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest("button")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ x: event.clientX, y: event.clientY, rotationX: rotation.x, rotationY: rotation.y });
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    setRotation({
      x: Math.max(-35, Math.min(25, drag.rotationX - (event.clientY - drag.y) * .12)),
      y: drag.rotationY + (event.clientX - drag.x) * .22,
    });
  };
  const changeZoom = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    setZoom((value) => Math.max(.55, Math.min(1.15, value - event.deltaY * .001)));
  };

  return (
    <div className="graph-layout">
      <div className="graph-toolbar">
        <div><strong>3D 知识星图</strong><span>中心主题 → 知识节点 → 知乎资料 · 横向可 360° 旋转 · 滚轮缩放</span></div>
        <div className="graph-legend" aria-label="图例"><span className="legend-before">前置</span><span className="legend-current">当前</span><span className="legend-after">进阶</span></div>
        <button className="graph-reset" type="button" onClick={() => { setRotation({ x: -5, y: -7 }); setZoom(.82); }}>重置视角</button>
      </div>
      <div className={`graph-viewport graph-radial${drag ? " is-dragging" : ""}`} onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={() => setDrag(null)} onPointerCancel={() => setDrag(null)} onWheel={changeZoom}>
        <div className="graph-halo" aria-hidden="true" />
        <div className="graph-world" style={{ transform: `scale(${zoom}) rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)` }}>
          {edges.map((edge) => <span className={`graph-edge edge-${edge.to.kind}`} key={edge.id} style={edgeStyle(edge)} />)}
          {nodes.map((node) => {
            const size = node.kind === "center" ? 116 : node.kind === "topic" ? 88 : 58;
            return (
              <button className={`graph-node graph-node-${node.stage} graph-node-${node.kind}${selected?.id === node.id ? " is-selected" : ""}`} key={node.id} type="button" style={{ transform: `translate3d(${node.x - size / 2}px, ${node.y - size / 2}px, ${node.z}px) rotateY(${-rotation.y}deg) rotateX(${-rotation.x}deg)` }} onClick={() => setSelectedId(node.id)} title={node.title} aria-pressed={selected?.id === node.id}>
                {node.kind !== "material" && <small>{stageName[node.stage]}</small>}<strong>{node.title}</strong>
              </button>
            );
          })}
        </div>
      </div>
      {selected && (
        <aside className={`graph-detail graph-detail-${selected.stage}`}>
          <div className="graph-detail-heading"><div><span>{selected.kind === "material" ? "知乎学习资料" : stageName[selected.stage]}</span><h3>{selected.title}</h3></div><b>{selected.difficulty}</b></div>
          <p>{selected.description}</p>
          {selected.kind !== "material" && selected.materials.length > 0 && <ul>{selected.materials.map((material) => <li key={`${material.title}-${material.url ?? "none"}`}>{material.url ? <a href={material.url} target="_blank" rel="noreferrer">{material.title}</a> : <strong>{material.title}</strong>}<small>{material.reason}</small></li>)}</ul>}
          {selected.kind === "material" && selected.material?.url && <a className="graph-open-link" href={selected.material.url} target="_blank" rel="noreferrer">在知乎查看原文 →</a>}
        </aside>
      )}
    </div>
  );
}
