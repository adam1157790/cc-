import { Layout, Menu } from "antd";
import {
  DashboardOutlined,
  FileTextOutlined,
  HistoryOutlined,
  LogoutOutlined,
  PictureOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function AppLayout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();

  const items = [
    { key: "/", icon: <VideoCameraOutlined />, label: "创作" },
    { key: "/images", icon: <PictureOutlined />, label: "文生图" },
    { key: "/history", icon: <HistoryOutlined />, label: "任务历史" },
    { key: "/storyboards", icon: <FileTextOutlined />, label: "分镜项目" },
    ...(user?.is_admin
      ? [{ key: "/admin", icon: <DashboardOutlined />, label: "管理后台" }]
      : []),
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider theme="dark" width={200}>
        <div
          style={{
            color: "#fff",
            padding: "18px 24px",
            fontSize: 17,
            fontWeight: 700,
            letterSpacing: 1,
          }}
        >
          🎬 文生视频
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[loc.pathname]}
          items={items}
          onClick={(e) => nav(e.key)}
        />
        <div style={{ position: "absolute", bottom: 16, width: 200 }}>
          <Menu
            theme="dark"
            mode="inline"
            selectable={false}
            items={[
              {
                key: "user",
                label: user?.quota_enabled === false
                  ? `${user?.username ?? ""}（无限制）`
                  : `${user?.username ?? ""}（${user?.quota_used_today ?? 0}/${user?.daily_quota ?? 0}）`,
              },
              { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: logout },
            ]}
          />
        </div>
      </Layout.Sider>
      <Layout.Content style={{ padding: 24, overflow: "auto" }}>
        <Outlet />
      </Layout.Content>
    </Layout>
  );
}
