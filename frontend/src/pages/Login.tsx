import { Button, Card, Form, Input, message, Tabs } from "antd";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const [loading, setLoading] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();

  const submit = async (mode: "login" | "register", values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await api.post<{ token: string }>(`/api/auth/${mode}`, values);
      localStorage.setItem("token", res.token);
      await refresh();
      nav("/");
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : "操作失败");
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async (values: { username: string; old_password: string; new_password: string }) => {
    setLoading(true);
    try {
      await api.post("/api/auth/reset-password", values);
      message.success("密码已重置，请用新密码登录");
      // 切回登录页并带上用户名
      const tabs = document.querySelector<HTMLButtonElement>(".ant-tabs-tab:nth-of-type(1)");
      tabs?.click();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : "重置失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
      }}
    >
      <Card style={{ width: 380 }} title={<div style={{ fontSize: 18 }}>🎬 文生视频创作平台</div>}>
        <Tabs
          centered
          items={[
            {
              key: "login",
              label: "登录",
              children: (
                <Form onFinish={(v) => submit("login", v)}>
                  <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                    <Input placeholder="用户名" size="large" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
                    <Input.Password placeholder="密码" size="large" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                    登录
                  </Button>
                </Form>
              ),
            },
            {
              key: "register",
              label: "注册",
              children: (
                <Form onFinish={(v) => submit("register", v)}>
                  <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                    <Input placeholder="用户名（2-64字符）" size="large" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, min: 6, message: "密码至少6位" }]}>
                    <Input.Password placeholder="密码（至少6位）" size="large" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                    注册
                  </Button>
                </Form>
              ),
            },
            {
              key: "reset",
              label: "重置密码",
              children: (
                <Form onFinish={resetPassword}>
                  <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                    <Input placeholder="用户名" size="large" />
                  </Form.Item>
                  <Form.Item name="old_password" rules={[{ required: true, message: "请输入旧密码" }]}>
                    <Input.Password placeholder="旧密码" size="large" />
                  </Form.Item>
                  <Form.Item
                    name="new_password"
                    rules={[
                      { required: true, message: "请输入新密码" },
                      { min: 6, message: "密码至少6位" },
                    ]}
                  >
                    <Input.Password placeholder="新密码（至少6位）" size="large" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                    重置密码
                  </Button>
                </Form>
              ),
            },
          ]}
        />
        <p style={{ color: "#999", fontSize: 12, textAlign: "center" }}>
          第一个注册的用户自动成为管理员
        </p>
      </Card>
    </div>
  );
}
