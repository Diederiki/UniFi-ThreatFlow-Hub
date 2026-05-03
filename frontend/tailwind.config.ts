import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // SOC dark palette — deep slate with neon accent
        bg:        "#0b0f17",
        panel:     "#111726",
        panel2:    "#161d2f",
        border:    "#1f2a44",
        muted:     "#7c8aa6",
        text:      "#dde4f1",
        accent:    "#22d3ee",  // cyan-400
        accent2:   "#7c3aed",  // violet-600
        success:   "#22c55e",
        warn:      "#f59e0b",
        danger:    "#ef4444",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34,211,238,0.25), 0 8px 32px -8px rgba(34,211,238,0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
