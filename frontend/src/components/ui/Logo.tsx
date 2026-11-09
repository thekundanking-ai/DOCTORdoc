import { LogoMark } from "./icons";

export function Logo({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark width={size === "sm" ? 24 : 28} height={size === "sm" ? 24 : 28} />
      <div className="leading-none">
        <span className="block text-[17px] font-semibold tracking-tight text-ink">DoctorDoc</span>
        <span className="block text-[11px] text-ink-sub">Consultation notes</span>
      </div>
    </div>
  );
}
