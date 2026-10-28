// 管理后台：统计概览 + 用户管理
import { useEffect, useState } from "react";
import { Button, Card, Col, message, InputNumber, Popconfirm, Row, Space, Switch, Table, Tag } from "antd";
import { api } from "../api";
import type { AdminStats } from "../api";

interface AdminUser {
  id: number;
  username: string;
  is_admin: boolean;
  daily_quota: number;
  quota_used_today: number;
  created_at: string | null;
}

export default function Admin() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [savingId, setSavingId] = useState<number | null>(null);

  const load = async () => {
    try {
      [setStats, setUsers] as const;
      setStats(await api.get<AdminStats>("/api/admin/stats"));
      setUsers(await api.get<AdminUser[]>("/api/admin/users"));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载失败");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateUser = async (id: number, patch: Record<string, unknown>) => {
    setSavingId(id);
    try {
      await api.patch(`/api/admin/users/${id}`, patch);
      await load();
      message.success("已保存");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSavingId(null);
    }
  };

  const deleteUser = async (id: number) => {
    try {
      await api.delete(`/api/admin/users/${id}`);
      await load();
      message.success("已删除");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  const maxDaily = Math.max(1, ...(stats?.daily.map((d) => d.count) ?? [1]));

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <Row gutter={16}>
        <Col span={6}>
          <Card><div style={{ fontSize: 28, fontWeight: 700 }}>{stats?.user_count ?? "-"}</div>用户</Card>
        </Col>
        <Col span={6}>
          <Card><div style={{ fontSize: 28, fontWeight: 700 }}>{stats?.task_count ?? "-"}</div>总任务</Card>
        </Col>
        <Col span={6}>
          <Card>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{stats?.by_status.succeeded ?? "-"}</div>成功
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#cf1322" }}>
              {stats?.by_status.failed ?? "-"}
            </div>失败
          </Card>
        </Col>
      </Row>

      <Card title="最近 7 天生成量" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 12, height: 120 }}>
          {stats?.daily.map((d) => (
            <div key={d.date} style={{ flex: 1, textAlign: "center" }}>
              <div
                style={{
                  height: `${(d.count / maxDaily) * 80}px`,
                  borderRadius: 4,
                  margin: "0 auto",
                  minHeight: d.count ? 4 : 1,
                  background: d.count ? "#1677ff" : "#eee",
                }}
              />
              <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>
                {d.date.slice(5)} · {d.count}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="用户管理" style={{ marginTop: 16 }}>
        <Table<AdminUser>
          rowKey="id"
          dataSource={users}
          pagination={false}
          size="middle"
          columns={[
            { title: "ID", dataIndex: "id", width: 60 },
            {
              title: "用户名",
              dataIndex: "username",
              render: (v, u) => (
                <Space>
                  {v}
                  {u.is_admin && <Tag color="gold">管理员</Tag>}
                </Space>
              ),
            },
            {
              title: "今日用量/配额",
              width: 180,
              render: (_, u) => (
                <Space>
                  <span>{u.quota_used_today}</span>/
                  <InputNumber
                    size="small"
                    min={0}
                    max={1000}
                    value={u.daily_quota}
                    disabled={savingId === u.id}
                    onBlur={(e) => {
                      const v = Number((e.target as HTMLInputElement).value);
                      if (v !== u.daily_quota) updateUser(u.id, { daily_quota: v });
                    }}
                    style={{ width: 80 }}
                  />
                </Space>
              ),
            },
            {
              title: "管理员",
              width: 100,
              render: (_, u) => (
                <Switch
                  checked={u.is_admin}
                  disabled={savingId === u.id}
                  onChange={(v) => updateUser(u.id, { is_admin: v })}
                />
              ),
            },
            {
              title: "注册时间",
              dataIndex: "created_at",
              width: 170,
              render: (v: string | null) => v?.slice(0, 19).replace("T", " ") ?? "-",
            },
            {
              title: "操作",
              width: 80,
              render: (_, u) => (
                <Popconfirm title={`删除用户 ${u.username} 及其所有任务？`} onConfirm={() => deleteUser(u.id)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
