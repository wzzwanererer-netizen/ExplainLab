export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  const p = {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (name) {
    case "dashboard":
      return <svg {...p}><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="3.5" rx="1" /><rect x="9" y="7.5" width="5" height="6.5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /></svg>;
    case "chat":
      return <svg {...p}><path d="M2.5 3.5h11a1 1 0 0 1 1 1v6.5a1 1 0 0 1-1 1H6l-3 2.5V12h-.5a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" /></svg>;
    case "knowledge":
      return <svg {...p}><path d="M3 2.5h7.5L13 5v8.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z" /><path d="M10 2.5V5.5h3M5 8h6M5 10.5h4.5" /></svg>;
    case "search":
      return <svg {...p}><circle cx="7.2" cy="7.2" r="4.7" /><path d="m10.8 10.8 3 3" /></svg>;
    case "map":
      return <svg {...p}><circle cx="3.5" cy="4" r="1.8" /><circle cx="12.5" cy="4" r="1.8" /><circle cx="8" cy="12" r="1.8" /><path d="M5.2 4.6 10.8 4.6M4.4 5.6 7.1 10.4M11.6 5.6 8.9 10.4" /></svg>;
    case "experiments":
      return <svg {...p}><path d="M6 2.5h4M6.8 2.5v3.8L3.2 12.2A1.2 1.2 0 0 0 4.2 14h7.6a1.2 1.2 0 0 0 1-1.8L9.2 6.3V2.5M5 10.5h6" /></svg>;
    case "reviews":
      return <svg {...p}><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" /><path d="m5.5 8.2 1.7 1.8 3.5-3.8" /></svg>;
    case "status":
      return <svg {...p}><path d="M2 8.5h2.8l1.6-4 2.4 7 1.6-3H14" /></svg>;
    case "palette":
      return <svg {...p}><path d="M8 2a6 6 0 1 0 0 12h.8a1.4 1.4 0 0 0 1.4-1.4c0-.5-.3-.9-.5-1.2-.2-.3-.1-.8.4-.9A4 4 0 0 0 14 8a6 6 0 0 0-6-6Z" /></svg>;
    case "sun":
      return <svg {...p}><circle cx="8" cy="8" r="2.8" /><path d="M8 1.8v1.4M8 12.8v1.4M1.8 8h1.4M12.8 8h1.4M3.6 3.6l1 1M11.4 11.4l1 1M12.4 3.6l-1 1M4.6 11.4l-1 1" /></svg>;
    case "moon":
      return <svg {...p}><path d="M12.8 10.2A5.3 5.3 0 0 1 5.8 3.2a5.5 5.5 0 1 0 7 7Z" /></svg>;
    case "panelLeft":
      return <svg {...p}><rect x="2" y="2.5" width="12" height="11" rx="1.5" /><path d="M5.8 2.5v11" /></svg>;
    case "bell":
      return <svg {...p}><path d="M4.2 6.5a3.8 3.8 0 1 1 7.6 0c0 3.2 1.2 4.3 1.2 4.3H3s1.2-1.1 1.2-4.3ZM6.6 13a1.5 1.5 0 0 0 2.8 0" /></svg>;
    case "upload":
      return <svg {...p}><path d="M8 10.5V3M5 5.8 8 2.8l3 3M2.5 11.5v1.3A1.2 1.2 0 0 0 3.7 14h8.6a1.2 1.2 0 0 0 1.2-1.2v-1.3" /></svg>;
    case "download":
      return <svg {...p}><path d="M8 3v7.5M5 7.7 8 10.7l3-3M2.5 11.5v1.3A1.2 1.2 0 0 0 3.7 14h8.6a1.2 1.2 0 0 0 1.2-1.2v-1.3" /></svg>;
    case "paperclip":
      return <svg {...p}><path d="m11.8 5.2-5.3 5.3a1.8 1.8 0 0 1-2.5-2.5l5.7-5.7a3 3 0 0 1 4.2 4.2l-5.7 5.7a4.2 4.2 0 0 1-6-6l5.1-5.1" /></svg>;
    case "link":
      return <svg {...p}><path d="M6.8 9.2a2.8 2.8 0 0 0 4 0l2-2a2.8 2.8 0 0 0-4-4L7.7 4.3M9.2 6.8a2.8 2.8 0 0 0-4 0l-2 2a2.8 2.8 0 1 0 4 4l1.1-1.1" /></svg>;
    default:
      return <svg {...p}><circle cx="8" cy="8" r="5" /></svg>;
  }
}
