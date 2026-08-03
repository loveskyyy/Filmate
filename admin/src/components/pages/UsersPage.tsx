import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Pencil, Trash2, Coins, Settings } from "lucide-react";
import { User, usersApi } from "../../api";

type UserRole = "admin" | "user";

interface UserForm {
  username: string;
  password: string;
  email: string;
  role: UserRole;
  credits: number;
}

const EMPTY_FORM: UserForm = { username: "", password: "", email: "", role: "user", credits: 0 };

export default function UsersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);
  
  // 积分调整
  const [showCreditsModal, setShowCreditsModal] = useState(false);
  const [creditsUser, setCreditsUser] = useState<User | null>(null);
  const [creditsAmount, setCreditsAmount] = useState(0);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await usersApi.list();
      setUsers(data);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      if (editingUser) {
        await usersApi.update(editingUser.id, form);
      } else {
        await usersApi.create(form);
      }
      setShowModal(false);
      setEditingUser(null);
      setForm(EMPTY_FORM);
      loadUsers();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除?")) return;
    try {
      await usersApi.delete(id);
      loadUsers();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    setForm({ username: user.username, password: "", email: user.email || "", role: user.role, credits: user.credits });
    setShowModal(true);
  };

  const openAdd = () => {
    setEditingUser(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  };
  
  // 积分调整
  const openCreditsModal = (user: User) => {
    setCreditsUser(user);
    setCreditsAmount(0);
    setShowCreditsModal(true);
  };
  
  // 打开用户智能体配置
  const openAgentConfig = (user: User) => {
    navigate(`/users/${user.id}/agent-config`);
  };
  
  const handleCreditsAdjust = async () => {
    if (!creditsUser || creditsAmount === 0) return;
    try {
      await fetch(`/api/v1/users/${creditsUser.id}/credits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: creditsAmount }),
      }).then(async (res) => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "调整失败");
        }
        return res.json();
      });
      setShowCreditsModal(false);
      setCreditsUser(null);
      loadUsers();
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">{t("users")}</h2>
        <button onClick={openAdd} className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          <Plus className="w-4 h-4" />
          {t("addUser")}
        </button>
      </div>

      {loading ? (
        <div className="text-gray-500">{t("loading")}...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("id")}</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("username")}</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("email")}</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("role")}</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("credits")}</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-500">{t("actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">{user.id}</td>
                  <td className="px-6 py-4">{user.username}</td>
                  <td className="px-6 py-4">{user.email || "-"}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded text-sm ${user.role === "admin" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-700"}`}>
                      {user.role === "admin" ? t("admin") : t("user")}
                    </span>
                  </td>
                  <td className="px-6 py-4">{user.credits}</td>
                  <td className="px-6 py-4">
                    <button onClick={() => openAgentConfig(user)} className="text-purple-600 hover:text-purple-800 mr-3" title={t("agentConfig")}>
                      <Settings className="w-4 h-4" />
                    </button>
                    <button onClick={() => openCreditsModal(user)} className="text-yellow-600 hover:text-yellow-800 mr-3" title={t("adjustCredits")}>
                      <Coins className="w-4 h-4" />
                    </button>
                    <button onClick={() => openEdit(user)} className="text-blue-600 hover:text-blue-800 mr-3">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => handleDelete(user.id)} className="text-red-600 hover:text-red-800">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-96">
            <h3 className="text-lg font-bold mb-4">
              {editingUser ? t("editUser") : t("addUser")}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">{t("username")}</label>
                <input
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  className="w-full border rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t("password")}</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder={editingUser ? "(不修改请留空)" : ""}
                  className="w-full border rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t("email")}</label>
                <input
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full border rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t("role")}</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
                  className="w-full border rounded px-3 py-2"
                >
                  <option value="user">{t("user")}</option>
                  <option value="admin">{t("admin")}</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t("credits")}</label>
                <input
                  type="number"
                  value={form.credits}
                  onChange={(e) => setForm({ ...form, credits: Number(e.target.value) })}
                  className="w-full border rounded px-3 py-2"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={handleSubmit} className="flex-1 bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700">
                {t("save")}
              </button>
              <button onClick={() => setShowModal(false)} className="flex-1 border py-2 rounded-lg hover:bg-gray-50">
                {t("cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 积分调整弹窗 */}
      {showCreditsModal && creditsUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 w-80">
            <h3 className="text-lg font-bold mb-4">{t("adjustCredits")}</h3>
            <p className="text-sm text-gray-600 mb-4">
              {creditsUser.username} - {t("currentCredits")}: {creditsUser.credits}
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">{t("adjustAmount")}</label>
                <input
                  type="number"
                  value={creditsAmount}
                  onChange={(e) => setCreditsAmount(Number(e.target.value))}
                  className="w-full border rounded px-3 py-2"
                  placeholder="正数增加，负数减少"
                />
              </div>
              <p className="text-sm text-gray-500">
                {t("newCredits")}: {creditsUser.credits + creditsAmount}
              </p>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={handleCreditsAdjust} className="flex-1 bg-yellow-500 text-white py-2 rounded-lg hover:bg-yellow-600">
                {t("confirm")}
              </button>
              <button onClick={() => setShowCreditsModal(false)} className="flex-1 border py-2 rounded-lg hover:bg-gray-50">
                {t("cancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
