import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

const inputBase =
  "w-full h-11 rounded-control border border-line bg-white px-3.5 text-sm text-ink " +
  "placeholder:text-ink-faint transition-colors " +
  "focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className = "", ...rest }, ref) => <input ref={ref} className={`${inputBase} ${className}`} {...rest} />
);
Input.displayName = "Input";

type FieldProps = {
  label: string;
  htmlFor?: string;
  error?: string;
  hint?: string;
  children: ReactNode;
};

export function Field({ label, htmlFor, error, hint, children }: FieldProps) {
  const autoId = useId();
  const id = htmlFor ?? autoId;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      <div>{children}</div>
      {error ? (
        <p className="text-[13px] text-danger">{error}</p>
      ) : hint ? (
        <p className="text-[13px] text-ink-sub">{hint}</p>
      ) : null}
    </div>
  );
}
