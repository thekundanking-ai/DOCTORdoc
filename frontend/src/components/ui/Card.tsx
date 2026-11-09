import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`rounded-card border border-line bg-card shadow-card ${className}`} {...rest}>
      {children}
    </div>
  );
}

type BadgeProps = { children: ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" };

const tones: Record<string, string> = {
  neutral: "bg-slate-100 text-ink-sub",
  success: "bg-green-50 text-success",
  warning: "bg-amber-50 text-warning",
  danger: "bg-red-50 text-danger",
  info: "bg-teal-50 text-primary",
};

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}
