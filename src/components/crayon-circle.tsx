"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const emptySubscribe = () => () => {};
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

export function CrayonCircle({ children }: { children: React.ReactNode }) {
  const isServer = useSyncExternalStore(emptySubscribe, getSnapshot, getServerSnapshot);
  const containerRef = useRef<HTMLSpanElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    if (isServer) return;
    
    const el = containerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      setDimensions({
        width: rect.width + 28,
        height: rect.height + 18,
      });
    };

    updateSize();

    const resizeObserver = new ResizeObserver(updateSize);
    resizeObserver.observe(el);

    const timer = setTimeout(() => setDrawn(true), 1400);

    return () => {
      clearTimeout(timer);
      resizeObserver.disconnect();
    };
  }, [isServer]);

  const pad = 5;
  const w = dimensions.width;
  const h = dimensions.height;
  const rx = w / 2;
  const ry = h / 2;
  const cx = rx;
  const cy = ry;

  // Rough ellipse path with slight wobble for crayon feel
  const generateRoughEllipse = () => {
    const segments = 24;
    let d = "";
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      const wobble = i % 3 === 0 ? 1.5 : i % 5 === 0 ? -1 : 0.5;
      const x = cx + (rx - pad + wobble) * Math.cos(angle);
      const y = cy + (ry - pad + wobble * 0.6) * Math.sin(angle);
      d += (i === 0 ? "M" : "L") + ` ${x.toFixed(1)} ${y.toFixed(1)}`;
    }
    d += " Z";
    return d;
  };

  const pathLength = 2 * Math.PI * Math.sqrt((rx * rx + ry * ry) / 2);

  if (isServer) {
    return <span className="relative inline-block">{children}</span>;
  }

  return (
    <span ref={containerRef} className="relative inline-block">
      {children}
      {w > 0 && h > 0 && (
        <svg
          className="absolute -inset-2 pointer-events-none"
          width={w + 16}
          height={h + 12}
          viewBox={`${-8} ${-6} ${w + 16} ${h + 12}`}
          fill="none"
          style={{
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
          }}
        >
          <defs>
            <filter id="crayon">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.08"
                numOctaves="3"
                result="noise"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="noise"
                scale="1.2"
                xChannelSelector="R"
                yChannelSelector="G"
              />
            </filter>
          </defs>
          <path
            d={generateRoughEllipse()}
            stroke="rgba(23, 23, 23, 0.35)"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            filter="url(#crayon)"
            style={{
              strokeDasharray: pathLength,
              strokeDashoffset: drawn ? 0 : pathLength,
              transition: "stroke-dashoffset 2.4s cubic-bezier(0.22, 0.61, 0.36, 1)",
            }}
          />
        </svg>
      )}
    </span>
  );
}
