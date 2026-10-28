import React, { useRef, useState } from "react";
import type { Annotation, Box, Point } from "./types";
import {
  rectangle,
  contains,
  clampPoint,
  moveBox,
  wholePage,
} from "./editorGeometry";
export type Tool =
  | "select"
  | "pan"
  | "annotation"
  | "floor"
  | "anchor"
  | "marquee";
type Props = {
  image: string;
  width: number;
  height: number;
  region?: Box | null;
  rotation: number;
  zoom: number;
  tool: Tool;
  annotations: Annotation[];
  selected: string[];
  showBoxes: boolean;
  showAnchors: boolean;
  onSelect: (ids: string[]) => void;
  onBox: (b: Box) => void;
  onAnchor: (p: Point) => void;
  onMove: (id: string, patch: Partial<Annotation>) => void;
};
export function PlanCanvas(p: Props) {
  const group = useRef<SVGGElement>(null),
    container = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<Box | null>(null);
  const drag = useRef<{
    start: Point;
    client: Point;
    id?: string;
    anchor?: boolean;
    box?: Box;
    point?: Point;
    scroll: [number, number];
  } | null>(null);
  const b = p.region || wholePage,
    w = p.width,
    h = p.height,
    cw = b.w * w,
    ch = b.h * h;
  const swapped = p.rotation === 90 || p.rotation === 270;
  const vw = swapped ? ch : cw,
    vh = swapped ? cw : ch;
  const transforms: Record<number, string> = {
    0: "",
    90: `translate(${ch},0) rotate(90)`,
    180: `translate(${cw},${ch}) rotate(180)`,
    270: `translate(0,${cw}) rotate(270)`,
  };
  function point(e: React.PointerEvent) {
    const m = group.current?.getScreenCTM();
    if (!m) return { x: 0, y: 0 };
    const q = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return clampPoint({ x: q.x / w, y: q.y / h });
  }
  function down(e: React.PointerEvent<SVGSVGElement>) {
    if (e.button !== 0 && e.button !== 1) return;
    e.preventDefault();
    const q = point(e),
      element = (e.target as Element).closest("[data-id]"),
      id = element?.getAttribute("data-id") || undefined;
    const a = p.annotations.find((a) => a.id === id);
    drag.current = {
      start: q,
      client: { x: e.clientX, y: e.clientY },
      id,
      anchor: element?.getAttribute("data-anchor") === "true",
      box: a?.bbox,
      point: a?.anchor || undefined,
      scroll: [container.current!.scrollLeft, container.current!.scrollTop],
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    if (p.tool === "select" && id)
      p.onSelect(e.shiftKey ? [...new Set([...p.selected, id])] : [id]);
  }
  function move(e: React.PointerEvent<SVGSVGElement>) {
    const d = drag.current;
    if (!d) return;
    if (p.tool === "pan" || e.buttons === 4) {
      container.current!.scrollLeft = d.scroll[0] - (e.clientX - d.client.x);
      container.current!.scrollTop = d.scroll[1] - (e.clientY - d.client.y);
      return;
    }
    if (["annotation", "floor", "marquee"].includes(p.tool))
      setDraft(rectangle(d.start, point(e)));
  }
  function up(e: React.PointerEvent<SVGSVGElement>) {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setDraft(null);
    const q = point(e),
      box = rectangle(d.start, q),
      distance = Math.hypot(e.clientX - d.client.x, e.clientY - d.client.y);
    if (p.tool === "anchor") {
      p.onAnchor(q);
      return;
    }
    if (
      ["annotation", "floor"].includes(p.tool) &&
      box.w * w > 3 &&
      box.h * h > 3
    ) {
      p.onBox(box);
      return;
    }
    if (p.tool === "marquee") {
      p.onSelect(
        p.annotations
          .filter((a) =>
            contains(box, {
              x: a.bbox.x + a.bbox.w / 2,
              y: a.bbox.y + a.bbox.h / 2,
            }),
          )
          .map((a) => a.id),
      );
      return;
    }
    if (p.tool === "select" && d.id && distance > 3) {
      if (d.anchor && d.point)
        p.onMove(d.id, {
          anchor: clampPoint({
            x: d.point.x + q.x - d.start.x,
            y: d.point.y + q.y - d.start.y,
          }),
          anchor_kind: "manual",
          target: null,
        });
      else if (d.box)
        p.onMove(d.id, {
          bbox: moveBox(d.box, q.x - d.start.x, q.y - d.start.y),
        });
    } else if (p.tool === "select" && !d.id) p.onSelect([]);
  }
  return (
    <div
      className={"plan-scroll tool-" + p.tool}
      ref={container}
      data-testid="plan-canvas"
    >
      <svg
        aria-label="Plan interactif"
        viewBox={`0 0 ${vw} ${vh}`}
        style={{ width: `${p.zoom}%`, aspectRatio: String(vw / vh) }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={() => {
          drag.current = null;
          setDraft(null);
        }}
      >
        <g
          ref={group}
          transform={`${transforms[p.rotation]} translate(${-b.x * w},${-b.y * h})`}
        >
          <image href={p.image} x={0} y={0} width={w} height={h} />
          {p.annotations.map((a, i) => {
            const active = p.selected.includes(a.id),
              color =
                a.status === "confirmed"
                  ? "#1c8062"
                  : a.status === "rejected"
                    ? "#858d9d"
                    : active
                      ? "#6549d5"
                      : "#c47a11";
            return (
              <g key={a.id} opacity={a.status === "rejected" ? 0.4 : 1}>
                {p.showBoxes && (
                  <g data-id={a.id}>
                    <rect
                      x={a.bbox.x * w}
                      y={a.bbox.y * h}
                      width={a.bbox.w * w}
                      height={a.bbox.h * h}
                      fill={active ? "#6549d52b" : "#ffc94a16"}
                      stroke={color}
                      strokeWidth={active ? 2.5 : 1.5}
                      vectorEffect="non-scaling-stroke"
                    />
                    <text
                      x={a.bbox.x * w}
                      y={a.bbox.y * h - 5}
                      fontSize={Math.max(12, vw / 65)}
                      fill={color}
                    >
                      {i + 1} · {a.text.slice(0, 24) || "Annotation"}
                    </text>
                  </g>
                )}
                {p.showAnchors && a.anchor && (
                  <g data-id={a.id} data-anchor="true">
                    <line
                      x1={(a.bbox.x + a.bbox.w / 2) * w}
                      y1={(a.bbox.y + a.bbox.h / 2) * h}
                      x2={a.anchor.x * w}
                      y2={a.anchor.y * h}
                      stroke={color}
                      strokeDasharray="5 4"
                      strokeWidth={1}
                      vectorEffect="non-scaling-stroke"
                    />
                    <circle
                      cx={a.anchor.x * w}
                      cy={a.anchor.y * h}
                      r={Math.max(7, vw / 100)}
                      fill="white"
                      stroke={color}
                      strokeWidth={2}
                      vectorEffect="non-scaling-stroke"
                    />
                    <circle
                      cx={a.anchor.x * w}
                      cy={a.anchor.y * h}
                      r={Math.max(2, vw / 350)}
                      fill={color}
                    />
                  </g>
                )}
              </g>
            );
          })}
          {draft && (
            <rect
              x={draft.x * w}
              y={draft.y * h}
              width={draft.w * w}
              height={draft.h * h}
              fill="#6549d522"
              stroke="#6549d5"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </g>
      </svg>
    </div>
  );
}
