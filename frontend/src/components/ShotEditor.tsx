// 分镜编辑器：多镜头列表 → 提交分镜 → 跳转分镜项目页
import { useEffect, useState } from "react";
import { Button, Card, Input, message, Select, Space } from "antd";
import { DeleteOutlined, PlusOutlined, SendOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ProviderInfo } from "../api";
import { useAuth } from "../auth";

interface Shot {
  key: number;
  prompt: string;
  duration: number;
}

let nextKey = 1;

export function ShotEditor() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [title, setTitle] = useState("未命名分镜");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [provider, setProvider] = useState("");
  const [ratio, setRatio] = useState("16:9");
  const [shots, setShots] = useState<Shot[]>([
    { key: nextKey++, prompt: "", duration: 5 },
  ]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get<ProviderInfo[]>("/api/tasks/providers").then((ps) => {
      setProviders(ps);
      if (ps.length) setProvider(ps[0].name);
    });
  }, []);

  const total = shots.reduce((s, x) => s + x.duration, 0);
  const needed = shots.filter((s) => s.prompt.trim()).length;

  const submit = async () => {
    const valid = shots.filter((s) => s.prompt.trim());
    if (!valid.length) return message.warning("至少填写一个镜头描述");
    if (!provider) return message.warning("请选择引擎");
    setSubmitting(true);
    try {
      await api.post<{ storyboard_id: string }>("/api/storyboards", {
        title,
        provider,
        aspect_ratio: ratio,
        shots: valid.map((s) => ({ prompt: s.prompt, duration: s.duration, optimize: true })),
      });
      message.success("分镜已提交，正在逐镜头生成");
      await refresh();
      nav(`/storyboards`);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      <Card>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Input
            size="large"
            placeholder="分镜标题"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
          <Space wrap>
            <span>引擎：</span>
            <Select
              style={{ width: 200 }}
              value={provider}
              onChange={setProvider}
              options={providers.map((p) => ({ value: p.name, label: p.label }))}
            />
            <span>比例：</span>
            <Select style={{ width: 110 }} value={ratio} onChange={setRatio} options={[
              { value: "16:9", label: "16:9" },
              { value: "9:16", label: "9:16" },
            ]} />
          </Space>

          {shots.map((shot, i) => (
            <Card
              key={shot.key}
              size="small"
              title={`镜头 ${i + 1}`}
              extra={
                shots.length > 1 && (
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => setShots(shots.filter((s) => s.key !== shot.key))}
                  />
                )
              }
            >
              <Space.Compact style={{ width: "100%" }}>
                <Input.TextArea
                  rows={2}
                  placeholder="这个镜头的画面描述（口语即可，会自动优化）"
                  value={shot.prompt}
                  onChange={(e) =>
                    setShots(shots.map((s) => (s.key === shot.key ? { ...s, prompt: e.target.value } : s)))
                  }
                />
              </Space.Compact>
              <Space style={{ marginTop: 8 }}>
                <span>时长：</span>
                <Select
                  style={{ width: 90 }}
                  value={shot.duration}
                  onChange={(v) =>
                    setShots(shots.map((s) => (s.key === shot.key ? { ...s, duration: v } : s)))
                  }
                  options={[
                    { value: 5, label: "5 秒" },
                    { value: 10, label: "10 秒" },
                  ]}
                />
              </Space>
            </Card>
          ))}

          <Button
            icon={<PlusOutlined />}
            onClick={() => setShots([...shots, { key: nextKey++, prompt: "", duration: 5 }])}
            block
          >
            添加镜头（最多20个）
          </Button>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#999" }}>
              共 {shots.length} 个镜头，已填 {needed} 个，成片约 {total} 秒；今日已用{" "}
              {user?.quota_used_today ?? 0}/{user?.daily_quota ?? 0}
            </span>
            <Button type="primary" size="large" icon={<SendOutlined />} onClick={submit} loading={submitting}>
              生成分镜成片
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  );
}
