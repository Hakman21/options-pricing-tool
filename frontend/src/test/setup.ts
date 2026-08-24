import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// Every request is intercepted. `onUnhandledRequest: "error"` means a component
// that starts calling a new endpoint fails the test rather than silently hitting
// the network.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

// ── Give jsdom a viewport ────────────────────────────────────────────────────
//
// jsdom does no layout, so every element measures 0 × 0. Recharts asks its
// container for a size, gets zero, refuses to draw, and warns - once per chart per
// render. Beyond the noise it also makes the charts pathologically slow to settle,
// which is what pushed one test past the default 5-second timeout on Windows.
//
// Reporting a fixed, plausible viewport instead lets the charts render normally.

const VIEWPORT = { width: 1024, height: 768 };
const CHART = { width: 800, height: 400 };

for (const [prop, value] of [
  ["offsetWidth", CHART.width],
  ["offsetHeight", CHART.height],
  ["clientWidth", CHART.width],
  ["clientHeight", CHART.height],
] as const) {
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    value,
  });
}

HTMLElement.prototype.getBoundingClientRect = function (): DOMRect {
  return {
    width: CHART.width,
    height: CHART.height,
    top: 0,
    left: 0,
    right: CHART.width,
    bottom: CHART.height,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect;
};

// Recharts' ResponsiveContainer measures through a ResizeObserver, which jsdom
// does not implement. The stub reports the size once on observe, which is all the
// container needs to commit to a width and height.
class ResizeObserverStub {
  constructor(private readonly callback: ResizeObserverCallback) {}

  observe(target: Element): void {
    this.callback(
      [
        {
          target,
          contentRect: {
            ...CHART,
            top: 0,
            left: 0,
            right: CHART.width,
            bottom: CHART.height,
            x: 0,
            y: 0,
          },
        } as unknown as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

Object.defineProperty(window, "innerWidth", {
  configurable: true,
  value: VIEWPORT.width,
});
Object.defineProperty(window, "innerHeight", {
  configurable: true,
  value: VIEWPORT.height,
});
