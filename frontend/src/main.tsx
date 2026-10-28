// 应用入口：路由 + 登录态守卫
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import AppLayout from "./pages/AppLayout";
import Login from "./pages/Login";
import Create from "./pages/Create";
import History from "./pages/History";
import Storyboards from "./pages/Storyboards";
import Admin from "./pages/Admin";
import ImageGen from "./pages/ImageGen";
import { AuthProvider, useAuth } from "./auth";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

createRoot(document.getElementById("root")!).render(
  <ConfigProvider locale={zhCN}>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
            <Route path="/" element={<Create />} />
            <Route path="/images" element={<ImageGen />} />
            <Route path="/history" element={<History />} />
            <Route path="/storyboards" element={<Storyboards />} />
            <Route path="/storyboards/:id" element={<Storyboards />} />
            <Route
              path="/admin"
              element={<RequireAdmin><Admin /></RequireAdmin>}
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </ConfigProvider>
);
