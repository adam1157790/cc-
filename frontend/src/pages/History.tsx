// 任务历史：轮询刷新进行中的任务，视频在线预览/下载
import { useCallback, useEffect, useState } from "react";
import { Button, Card, Col, Empty, message, Modal, Popconfirm, Row, Space, Tag } from "antd";
import { DownloadOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, mediaUrl } from "../api";
import type { TaskOut } from "../api";

const STATUS: Record<TaskOut["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  running: { color: "processing", label: "生成中" },
  succeeded: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
  canceled: { color: "warning", label: "已取消" },
};

export default function History() {
  const [tasks, setTasks] = useState<TaskOut[]>([]);
  const [playing, setPlaying] = useState<TaskOut | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setTasks(await api.get<TaskOut[]>("/api/tasks"));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
    // 有进行中任务时每5秒轮询
    const timer = setInterval(() => {
      if (tasks.some((t) => t.status === "pending" || t.status === "running")) load();
    }, 5000);
    return () => clearInterval(timer);
  }, [load, tasks]);

  const cancel = async (id: string) => {
    try {
      await api.post(`/api/tasks/${id}/cancel`);
      load();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "取消失败");
    }
  };

  const del = async (id: string) => {
    try {
      await api.delete(`/api/tasks/${id}`);
      load();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  if (loading) return null;
  if (!tasks.length)
    return <Empty description="还没有生成任务，去创作页开始吧" style={{ marginTop: 100 }} />;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={() => { setLoading(true); load().finally(() => setLoading(false)); }}>
          刷新
        </Button>
      </Space>
      <Row gutter={[16, 16]}>
        {tasks.map((t) => (
          <Col key={t.id} xs={24} sm={12} lg={8}>
            <Card
              size="small"
              hoverable
              cover={
                t.has_video ? (
                  <video
                    src={mediaUrl(`/api/tasks/${t.id}/video`)}
                    style={{ height: 180, objectFit: "cover", background: "#000" }}
                    preload="metadata"
                  />
                ) : (
                  <div
                    style={{
                      height: 180,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: "#fafafa",
                      color: "#bbb",
                    }}
                  >
                    {t.status === "failed" ? "❌ 生成失败" : t.status === "canceled" ? "已取消" : `${t.progress}%`}
                  </div>
                )
              }
              actions={[
                t.has_video ? (
                  <PlayCircleOutlined key="play" onClick={() => setPlaying(t)} />
                ) : (
                  <span key="none" style={{ color: "#ccc" }}>—</span>
                ),
                t.has_video ? (
                  <a key="dl" href={mediaUrl(`/api/tasks/${t.id}/video`)} download>
                    <DownloadOutlined />
                  </a>
                ) : (
                  <span key="none2" style={{ color: "#ccc" }}>—</span>
                ),
                (t.status === "pending" || t.status === "running") && (
                  <Popconfirm
                    key="cancel"
                    title="确定取消该任务？"
                    onConfirm={() => cancel(t.id)}
                  >
                    <a style={{ color: "#faad14" }}>取消</a>
                  </Popconfirm>
                ),
                t.status !== "pending" && t.status !== "running" && (
                  <Popconfirm key="del" title="删除任务及视频？" onConfirm={() => del(t.id)}>
                    <a style={{ color: "#ff4d4f" }}>删除</a>
                  </Popconfirm>
                ),
              ].filter(Boolean)}
            >
              <Card.Meta
                title={
                  <Space>
                    <Tag color={STATUS[t.status].color}>{STATUS[t.status].label}</Tag>
                    <span style={{ fontSize: 12, color: "#999" }}>
                      {t.duration}s · {t.aspect_ratio} · {t.task_type === "i2v" ? "图生" : "文生"}
                    </span>
                  </Space>
                }
                description={
                  <span style={{ display: "block", height: 40, overflow: "hidden" }}>
                    {t.prompt.slice(0, 60)}
                    {t.error && <div style={{ color: "#ff4d4f" }}>{t.error.slice(0, 80)}</div>}
                  </span>
                }
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        open={!!playing}
        onCancel={() => setPlaying(null)}
        footer={null}
        width={800}
        title={playing?.prompt.slice(0, 40)}
        destroyOnClose
      >
        {playing && (
          <div>
            <video
              src={mediaUrl(`/api/tasks/${playing.id}/video`)}
              controls
              autoPlay
              style={{ width: "100%" }}
            />
            {playing.optimized_prompt && (
              <div style={{ marginTop: 12 }}>
                <p style={{ fontWeight: 600 }}>优化后提示词</p>
                <p style={{ color: "#666", fontSize: 13 }}>{playing.optimized_prompt}</p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
