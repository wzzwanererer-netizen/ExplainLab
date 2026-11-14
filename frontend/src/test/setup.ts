import "@testing-library/jest-dom/vitest";

// React Flow 依赖 ResizeObserver / DOMMatrixReadOnly，jsdom 未提供，补最小 polyfill。
// 组件单测中画布另用确定性替身（见 KnowledgeMap.test.tsx），真实画布以浏览器验收为准。
class ResizeObserverPolyfill {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

class DOMMatrixReadOnlyPolyfill {
  m11 = 1;
  m12 = 0;
  m21 = 0;
  m22 = 1;
  m41 = 0;
  m42 = 0;
}

const globals = globalThis as unknown as Record<string, unknown>;
if (!("ResizeObserver" in globalThis)) {
  globals.ResizeObserver = ResizeObserverPolyfill;
}
if (!("DOMMatrixReadOnly" in globalThis)) {
  globals.DOMMatrixReadOnly = DOMMatrixReadOnlyPolyfill;
}