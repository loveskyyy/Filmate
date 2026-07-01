import { useTranslation } from "react-i18next";

export default function ConfigPage() {
  const { t } = useTranslation();

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">{t("config")}</h2>

      <div className="bg-white rounded-lg shadow p-6 max-w-2xl">
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t("siteName")}
            </label>
            <input
              type="text"
              defaultValue="Filmate"
              className="w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t("maxProjectsPerUser")}
            </label>
            <input
              type="number"
              defaultValue="10"
              className="w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" id="allowSignup" defaultChecked className="w-4 h-4" />
            <label htmlFor="allowSignup">{t("allowSignup")}</label>
          </div>

          <button className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">
            {t("save")}
          </button>
        </div>
      </div>
    </div>
  );
}
