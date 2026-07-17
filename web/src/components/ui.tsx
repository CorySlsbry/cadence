import * as React from "react";
import { cn } from "@/lib/utils";

export function Button({
  className,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline";
}) {
  const variants = {
    primary:
      "bg-[var(--accent)] text-black hover:brightness-95 disabled:opacity-40 disabled:cursor-not-allowed",
    ghost: "bg-transparent text-white/80 hover:bg-white/5",
    outline: "border border-[var(--border-strong)] text-white hover:bg-white/5",
  };
  return (
    <button
      className={cn(
        // press = scale(0.97) feedback; transitions name their properties (never `all`).
        "press inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold",
        "transition-[background-color,border-color,filter,opacity] duration-150",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full min-h-11 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white",
        "placeholder:text-white/30 outline-none transition-[border-color,box-shadow] duration-150",
        "focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn("mb-1.5 block text-xs font-medium text-white/65", className)} {...props} />
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-4 sm:p-6",
        className,
      )}
      {...props}
    />
  );
}

export function Switch({
  checked,
  onCheckedChange,
  className,
  ...props
}: Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "type"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        // The knob is a normal in-flow child of a padded track — never absolutely
        // positioned. An absolute knob with no left anchor resolves its static
        // position against the button's centred text alignment and renders ~22px
        // too far right (escaping the track entirely when on).
        "inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full p-0.5",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        checked ? "bg-[var(--accent)]" : "bg-white/15",
        className,
      )}
      {...props}
    >
      {/* track content box = 44 - 2*2 = 40px; knob 20px => 20px of travel */}
      <span
        className={cn(
          "block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]",
          checked && "translate-x-5",
        )}
      />
    </button>
  );
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "accent" | "good" | "bad" }) {
  const tones = {
    neutral: "bg-white/8 text-white/60",
    accent: "bg-[var(--accent)]/15 text-[var(--accent)]",
    good: "bg-emerald-500/15 text-emerald-300",
    bad: "bg-red-500/15 text-red-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
