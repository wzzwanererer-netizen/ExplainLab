import { useEffect, useRef } from "react";

export interface ContextMenuItem {
  id: string;
  label: string;
  danger?: boolean;
  dividerBefore?: boolean;
  onClick: () => void;
}

export interface ContextMenuState {
  x: number;
  y: number;
  items: ContextMenuItem[];
}

interface Props {
  menu: ContextMenuState | null;
  onClose: () => void;
}

/**
 * 原生桌面风格右键上下文菜单：自动防视口溢出，支持 Esc 与外部点击关闭。
 */
export function ContextMenu({ menu, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointer = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("scroll", onClose, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("scroll", onClose, true);
    };
  }, [menu, onClose]);

  if (!menu) return null;

  const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const left = Math.min(menu.x, Math.max(8, vw - 210));
  const top = Math.min(menu.y, Math.max(8, vh - menu.items.length * 36 - 24));

  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-[70] min-w-[184px] rounded-xl border p-1.5 shadow-xl backdrop-blur-md"
      style={{
        left,
        top,
        background: "var(--nesti-surface-1, #ffffff)",
        borderColor: "var(--nesti-border-strong, #cbd5e1)",
      }}
    >
      {menu.items.map((item) => (
        <div key={item.id}>
          {item.dividerBefore && (
            <div
              className="my-1 border-t"
              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
            />
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onClose();
              item.onClick();
            }}
            className={`flex w-full items-center rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
              item.danger
                ? "text-red-500 hover:bg-red-500/10"
                : "hover:bg-[var(--nesti-surface-hover,rgba(148,163,184,0.16))]"
            }`}
            style={
              item.danger
                ? undefined
                : { color: "var(--nesti-text-primary, #0f172a)" }
            }
          >
            {item.label}
          </button>
        </div>
      ))}
    </div>
  );
}
