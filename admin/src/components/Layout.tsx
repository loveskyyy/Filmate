import { useState, useRef, useEffect } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Users, Settings, BarChart3, LogOut, ChevronDown } from "lucide-react";
import clsx from "clsx";
import { clearToken } from "@/api";

const navItems = [
  { path: "/users", label: "users", icon: Users },
  { path: "/config", label: "config", icon: Settings },
  { path: "/stats", label: "stats", icon: BarChart3 },
];

export default function Layout() {
  const { t } = useTranslation();
  const location = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    clearToken();
    window.location.href = "/login";
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold">Filmate Admin</h1>
          {/* 用户下拉菜单 */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white font-medium">
                A
              </div>
              <span className="text-sm text-gray-700">Admin</span>
              <ChevronDown className={clsx("w-4 h-4 text-gray-400 transition-transform", dropdownOpen && "rotate-180")} />
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border py-1 z-50">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  {t("logout")}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main */}
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 bg-white shadow h-[calc(100vh-64px)]">
          <nav className="p-4 space-y-1">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className={clsx(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                  location.pathname === path
                    ? "bg-blue-50 text-blue-600"
                    : "text-gray-600 hover:bg-gray-50"
                )}
              >
                <Icon className="w-5 h-5" />
                {t(label)}
              </Link>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
