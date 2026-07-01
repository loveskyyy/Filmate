import { Routes, Route, Navigate } from "react-router-dom";
import UsersPage from "./components/pages/UsersPage";
import ConfigPage from "./components/pages/ConfigPage";
import StatsPage from "./components/pages/StatsPage";
import LoginPage from "./components/pages/LoginPage";
import Layout from "./components/Layout";
import { getToken } from "./api";

// 保护路由：未登录跳转到登录页
function ProtectedRoute({ children }: { children: JSX.Element }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/users" replace />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="config" element={<ConfigPage />} />
        <Route path="stats" element={<StatsPage />} />
      </Route>
    </Routes>
  );
}
