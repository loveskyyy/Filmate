import { useTranslation } from "react-i18next";
import { Users, FolderOpen, ListTodo, Activity } from "lucide-react";

const stats = [
  { label: "totalUsers", value: 128, icon: Users, color: "bg-blue-500" },
  { label: "totalProjects", value: 512, icon: FolderOpen, color: "bg-green-500" },
  { label: "totalTasks", value: 2048, icon: ListTodo, color: "bg-purple-500" },
  { label: "apiCalls", value: "15.2K", icon: Activity, color: "bg-orange-500" },
];

export default function StatsPage() {
  const { t } = useTranslation();

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">{t("stats")}</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <div className={`${color} p-3 rounded-lg`}>
                <Icon className="w-6 h-6 text-white" />
              </div>
            </div>
            <div className="text-3xl font-bold text-gray-900">{value}</div>
            <div className="text-gray-500 mt-1">{t(label)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
