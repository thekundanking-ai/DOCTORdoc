import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Logo } from "../ui/Logo";
import { LogoutIcon } from "../ui/icons";
import { Button } from "../ui/Button";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/patients", label: "Patients", end: false },
];

const NavGlyph = ({ label }: { label: string }) => (
  <span className="flex h-5 w-5 items-center justify-center text-base leading-none" aria-hidden>
    {label === "Dashboard" ? "⌂" : "☰"}
  </span>
);

export function AppShell() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  function logout() {
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-page">
      <div className="flex">
        {/* Sidebar (desktop) */}
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-card px-4 py-5 md:flex">
          <div className="px-2">
            <Logo />
          </div>
          <nav className="mt-8 space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-control px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive ? "bg-primary-soft text-primary" : "text-ink-sub hover:bg-slate-50 hover:text-ink"
                  }`
                }
              >
                <NavGlyph label={item.label} />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto">
            <Button variant="secondary" size="sm" fullWidth onClick={logout}>
              <LogoutIcon width={17} height={17} /> Log out
            </Button>
          </div>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col md:pl-60">
          <header className="sticky top-0 z-20 flex h-[68px] items-center justify-between border-b border-line bg-card px-4 md:px-8">
            <div className="md:hidden">
              <Logo size="sm" />
            </div>
            <div className="hidden text-sm text-ink-sub md:block">Clinic workspace</div>
            <div className="relative">
              <Button variant="ghost" size="sm" onClick={() => setMenuOpen((v) => !v)} aria-haspopup="menu" aria-expanded={menuOpen}>
                Dr. Anitha Rao
              </Button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-card border border-line bg-card p-1.5 shadow-pop">
                  <button
                    onClick={logout}
                    className="flex w-full items-center gap-2 rounded-control px-3 py-2 text-sm text-danger hover:bg-red-50"
                  >
                    <LogoutIcon width={17} height={17} /> Log out
                  </button>
                </div>
              )}
            </div>
          </header>

          <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
            <Outlet />
          </main>
        </div>
      </div>

      {/* Mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-card md:hidden">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium ${
                isActive ? "text-primary" : "text-ink-sub"
              }`
            }
          >
            <NavGlyph label={item.label} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="h-16 md:hidden" />
    </div>
  );
}
