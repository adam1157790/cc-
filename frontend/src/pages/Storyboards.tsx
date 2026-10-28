// 分镜项目：列表 + 详情（镜头进度、失败重试、成片播放/下载）
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  message,
  Modal,
  Progress,
  Row,
  Space,
  Tag,
  Tooltip,
} from "antd";
import { ArrowLeftOutlined, DownloadOutlined, PlayCircleOutlined, RedoOutlined } from "@ant-design/icons";
import { api, mediaUrl } from "../api";
import type { StoryboardOut } from "../api";
import { useAuth } from "../auth";
import { useNavigate, useParams } from "react-router-dom";

const SB_STATUS: Record<StoryboardOut["status"], { color: string; label: string }> = {
  draft: { color: "default", label: "草稿" },
  generating: { color: "processing", label: "生成中" },
  done: { color: "success", label: "已完成" },
  partial: { color: "warning", label: "部分失败" },
};

export default function Storyboards() {
  const { id } = useParams();
  return id ? <StoryboardDetail id={id} /> : <StoryboardList />;
}

function StoryboardList() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sbs, setSbs] = useState<StoryboardOut[]>([]);
  const [allUsers, setAllUsers] = useState(false);

  const load = useCallback(async () => {
    try {
      const qs = allUsers && user?.is_admin ? "?all_users=true" : "";
      setSbs(await api.get<StoryboardOut[]>(`/api/storyboards${qs}`));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载失败");
    }
  }, [allUsers, user?.is_admin]);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (sbs.some((s) => s.status === "generating")) load();
    }, 5000);
    return () => clearInterval(timer);
  }, [load, sbs]);

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto" }}>
      {user?.is_admin && (
        <div style={{ marginBottom: 16, textAlign: "right" }}>
          <Checkbox
            checked={allUsers}
            onChange={(e) => setAllUsers(e.target.checked)}
          >
            查看所有用户的分镜
          </Checkbox>
        </div>
      )}
      {!sbs.length ? (
        <Empty description="还没有分镜项目，去创作页提交一个吧" style={{ marginTop: 100 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {sbs.map((s) => (
            <Col key={s.id} xs={24} sm={12} md={8}>
              <Card hoverable onClick={() => nav(`/storyboards/${s.id}`)}>
                <Card.Meta
                  title={
                    <Space>
                      <Tag color={SB_STATUS[s.status].color}>{SB_STATUS[s.status].label}</Tag>
                      {s.title}
                    </Space>
                  }
                  description={
                    <>
                      <div>{s.shot_count} 个镜头</div>
                      {allUsers && s.owner && <div>用户：{s.owner}</div>}
                      {s.error && <div style={{ color: "#faad14" }}>{s.error}</div>}
                      <div style={{ color: "#999", fontSize: 12 }}>
                        {s.created_at?.slice(0, 19).replace("T", " ")}
                      </div>
                    </>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}

function StoryboardDetail({ id }: { id: string }) {
  const nav = useNavigate();
  const [sb, setSb] = useState<StoryboardOut | null>(null);
  const [playing, setPlaying] = useState(false);

  const load = useCallback(async () => {
    try {
      setSb(await api.get<StoryboardOut>(`/api/storyboards/${id}`));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载失败");
    }
  }, [id]);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (sb?.status === "generating") load();
    }, 5000);
    return () => clearInterval(timer);
  }, [load, sb?.status]);

  const retry = async (shotIndex: number) => {
    try {
      await api.post(`/api/storyboards/${id}/shots/${shotIndex}/retry`);
      message.success("已重新提交该镜头");
      load();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "重试失败");
    }
  };

  if (!sb) return null;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => nav("/storyboards")}>
          返回列表
        </Button>
        <h2 style={{ margin: 0 }}>{sb.title}</h2>
        <Tag color={SB_STATUS[sb.status].color}>{SB_STATUS[sb.status].label}</Tag>
        {sb.owner && <Tag color="blue">用户：{sb.owner}</Tag>}
      </Space>

      {sb.has_final_video && (
        <Card title="成片" style={{ marginBottom: 16 }} extra={
          <Space>
            <Button icon={<PlayCircleOutlined />} type="primary" onClick={() => setPlaying(true)}>
              播放成片
            </Button>
            <Button icon={<DownloadOutlined />} href={mediaUrl(`/api/storyboards/${id}/final-video`)} download>
              下载
            </Button>
          </Space>
        }>
          <video
            src={mediaUrl(`/api/storyboards/${id}/final-video`)}
            style={{ width: "100%", borderRadius: 8 }}
            controls
          />
        </Card>
      )}

      <Row gutter={[12, 12]}>
        {sb.shots?.map((shot) => (
          <Col key={shot.task_id} xs={24} md={12}>
            <Card
              size="small"
              title={`镜头 ${shot.shot_index + 1}（${shot.duration}s）`}
              extra={
                shot.status === "failed" && (
                  <Tooltip title="重试该镜头">
                    <Button size="small" icon={<RedoOutlined />} onClick={() => retry(shot.shot_index)}>
                      重试
                    </Button>
                  </Tooltip>
                )
              }
            >
              {shot.has_video ? (
                <video
                  src={mediaUrl(`/api/tasks/${shot.task_id}/video`)}
                  style={{ width: "100%", borderRadius: 6 }}
                  controls
                  preload="metadata"
                />
              ) : shot.status === "failed" ? (
                <div style={{ color: "#ff4d4f", padding: 20, textAlign: "center" }}>
                  失败：{shot.error?.slice(0, 100)}
                </div>
              ) : (
                <div style={{ padding: 20 }}>
                  <Progress percent={shot.progress} status="active" />
                </div>
              )}
              <p style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
                {shot.prompt.slice(0, 80)}
              </p>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        open={playing}
        onCancel={() => setPlaying(false)}
        footer={null}
        width={860}
        title={`${sb.title} — 成片`}
      >
        <video
          src={mediaUrl(`/api/storyboards/${id}/final-video`)}
          controls
          autoPlay
          style={{ width: "100%" }}
        />
      </Modal>
    </div>
  );
}
