import * as React from "react";

/**
 * On phones: pins its children to the bottom of the viewport as a safe-area-aware
 * action bar. On sm+ it dissolves into normal flow (static, no border/bg).
 */
export function StickyActionBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--border)] bg-[var(--background)]/95 px-4 pt-3 backdrop-blur [padding-bottom:calc(0.75rem+env(safe-area-inset-bottom))] sm:static sm:z-auto sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
      <div className="mx-auto w-full max-w-6xl text-center">{children}</div>
    </div>
  );
}
