"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import clsx from "clsx";

type ToastVariant = "info" | "success" | "warn" | "danger";
type Toast = { id: number; message: string; variant: ToastVariant };

type ToastCtx = {
  push: (message: string, variant?: ToastVariant) => void;
};

const Ctx = createContext<ToastCtx | null>(null);

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be inside <ToastProvider>");
  return ctx;
}

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  const push = useCallback((message: string, variant: ToastVariant = "info") => {
    const id = nextId++;
    setItems((s) => [...s, { id, message, variant }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 4000);
  }, []);

  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {items.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "px-3 py-2 rounded-md border text-sm shadow-glow backdrop-blur",
              t.variant === "success" && "bg-success/10 text-success border-success/40",
              t.variant === "warn" && "bg-warn/10 text-warn border-warn/40",
              t.variant === "danger" && "bg-danger/10 text-danger border-danger/40",
              t.variant === "info" && "bg-panel/80 text-text border-border",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
