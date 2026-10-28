// 文生图页：与视频创作页完全独立（独立配额、独立历史）
// 「精确输出」四件套：AI结构化扩写提示词 / 精确尺寸 / 固定seed复现 / 提示词遵循度
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Row,
  Select,
  Slider,
  Space,
  Tag,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  SendOutlined,
  ThunderboltFilled,
} from "@ant-design/icons";
import { api, mediaUrl } from "../api";
import type {
  ImageOptimizeResult,
  ImageProviderInfo,
  ImageQuota,
  ImageTaskOut,
} from "../api";

const SIZE_OPTIONS = [
  { value: "1:1", label: "1:1 方形" },
  { value: "16:9", label: "16:9 横屏" },
  { value: "9:16", label: "9:16 竖屏" },
  { value: "4:3", label: "4:3 横幅" },
  { value: "3:4", label: "3:4 竖幅" },
];

const STATUS: Record<ImageTaskOut["status"], { color: string; label: string }> = {
  pending: { color: "default", label: "排队中" },
  running: { color: "processing", label: "生成中" },
  succeeded: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
  canceled: { color: "warning", label: "已取消" },
};

export default function ImageGen() {
  const [providers, setProviders] = useState<ImageProviderInfo[]>([]);
  const [provider, setProvider] = useState("");
  const [quota, setQuota] = useState<ImageQuota | null>(null);
  const [prompt, setPrompt] = useState("");
  const [optimized, setOptimized] = useState<ImageOptimizeResult | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [size, setSize] = useState("1:1");
  const [seed, setSeed] = useState<number | null>(null);
  const [guidance, setGuidance] = useState(0);
  const [candidates, setCandidates] = useState(1);
  const [autoOptimize, setAutoOptimize] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [tasks, setTasks] = useState<ImageTaskOut[]>([]);

  const refreshQuota = useCallback(async () => {
    try {
      setQuota(await api.get<ImageQuota>("/api/images/quota"));
    } catch {
      /* 忽略：不影响主流程 */
    }
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      setTasks(await api.get<ImageTaskOut[]>("/api/images"));
    } catch {
      /* 静默失败：轮询场景 */
    }
  }, []);

  useEffect(() => {
    api.get<ImageProviderInfo[]>("/api/images/providers").then((ps) => {
      setProviders(ps);
      if (ps.length) setProvider(ps[0].name);
    });
    refreshQuota();
    loadTasks();
  }, [refreshQuota, loadTasks]);

  // 有进行中任务时每3秒轮询（图片生成比视频快）
  useEffect(() => {
    const timer = setInterval(() => {
      if (tasks.some((t) => t.status === "pending" || t.status === "running")) {
        loadTasks();
        refreshQuota();
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [tasks, loadTasks, refreshQuota]);

  const doOptimize = async () => {
    if (!prompt.trim()) return message.warning("请先输入描述");
    setOptimizing(true);
    try {
      setOptimized(await api.post<ImageOptimizeResult>("/api/images/optimize", { prompt }));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "优化失败");
    } finally {
      setOptimizing(false);
    }
  };

  const submit = async () => {
    if (!prompt.trim()) return message.warning("请输入描述");
    if (!provider) return message.warning("请选择引擎");
    setSubmitting(true);
    try {
      const res = await api.post<{ task_ids: string[] }>("/api/images", {
        prompt,
        provider,
        size,
        seed,
        guidance,
        optimize: autoOptimize,
        candidates,
      });
      message.success(`已提交${res.task_ids.length > 1 ? ` ${res.task_ids.length} 张候选` : "生成任务"}`);
      setOptimized(null);
      await Promise.all([loadTasks(), refreshQuota()]);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const del = async (id: string) => {
    try {
      await api.delete(`/api/images/${id}`);
      loadTasks();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {providers.length === 0 && (
        <Alert
          type="warning"
          showIcon
          message="未检测到可用的文生图引擎"
          description="文生图复用视频引擎的 API Key：在 .env 中配置 VOLCENGINE_API_KEY 或 ZHIPU_API_KEY 后重启服务即可"
          style={{ marginBottom: 16 }}
        />
      )}
      <Card title="🎨 文生图" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Input.TextArea
            rows={3}
            placeholder="描述想要的画面，例如：一张复古胶片质感的街角咖啡店招牌，黄昏暖光……需要精确出现的文字/数量/颜色请直接写明，系统会严格保留"
            value={prompt}
            onChange={(e) => { setPrompt(e.target.value); setOptimized(null); }}
            maxLength={2000}
            showCount
          />

          <Space>
            <Button icon={<ThunderboltFilled />} onClick={doOptimize} loading={optimizing}>
              AI 优化提示词
            </Button>
            <Checkbox checked={autoOptimize} onChange={(e) => setAutoOptimize(e.target.checked)}>
              提交时自动优化
            </Checkbox>
          </Space>
          {optimized && (
            <Card size="small" style={{ background: "#f6ffed" }}>
              <p style={{ fontWeight: 600 }}>优化后的提示词：</p>
              <p>{optimized.optimized_prompt}</p>
              {optimized.negative_prompt && (
                <p style={{ color: "#999", fontSize: 12 }}>负面词：{optimized.negative_prompt}</p>
              )}
            </Card>
          )}

          <Space wrap size={16}>
            <span>引擎：</span>
            <Select
              style={{ width: 220 }}
              value={provider}
              onChange={setProvider}
              options={providers.map((p) => ({ value: p.name, label: p.label }))}
              placeholder="选择引擎"
            />
            <span>尺寸：</span>
            <Select style={{ width: 130 }} value={size} onChange={setSize} options={SIZE_OPTIONS} />
            <span>张数：</span>
            <Select style={{ width: 130 }} value={candidates} onChange={setCandidates} options={[
              { value: 1, label: "1 张（省配额）" },
              { value: 2, label: "2 张候选" },
              { value: 3, label: "3 张候选" },
              { value: 4, label: "4 张候选" },
            ]} />
          </Space>

          <Space wrap size={16}>
            <span>Seed（固定可复现）：</span>
            <InputNumber
              value={seed}
              onChange={(v) => setSeed(v)}
              placeholder="留空随机"
              min={0}
              max={2147483647}
              style={{ width: 160 }}
            />
            <span style={{ color: "#999", fontSize: 12 }}>
              同一提示词 + 同一 Seed = 精确复现同一画面
            </span>
          </Space>

          <div>
            <Space>
              <span>提示词遵循度：</span>
              <Slider
                style={{ width: 220, margin: "0 8px" }}
                min={0}
                max={100}
                value={guidance}
                onChange={setGuidance}
                marks={{ 0: "默认", 100: "严格" }}
              />
            </Space>
            <div style={{ color: "#999", fontSize: 12, marginTop: -8 }}>
              越高越严格贴合提示词（过高可能牺牲画面质量，火山 Seedream 支持）
            </div>
          </div>

          <div style={{ textAlign: "right", color: "#999" }}>
            {quota?.unlimited
              ? "今日文生图：无限制（与视频配额相互独立）"
              : `今日文生图已用 ${quota?.used ?? 0} / ${quota?.quota ?? "-"}（与视频配额相互独立）`}
          </div>

          <Button
            type="primary"
            size="large"
            icon={<SendOutlined />}
            onClick={submit}
            loading={submitting}
            disabled={!provider}
            block
          >
            开始生成{candidates > 1 ? `（${candidates}张候选）` : ""}
          </Button>
        </Space>
      </Card>

      <Card title="我的图片" extra={
        <span style={{ color: "#999", fontSize: 12 }}>共 {tasks.length} 张</span>
      }>
        {!tasks.length && <Empty description="还没有生成图片" />}
        <Row gutter={[16, 16]}>
          {tasks.map((t) => (
            <Col key={t.id} xs={24} sm={12} md={8}>
              <Card
                size="small"
                hoverable
                cover={
                  t.has_image ? (
                    <img
                      src={mediaUrl(`/api/images/${t.id}/file`)}
                      alt={t.prompt.slice(0, 30)}
                      style={{ height: 200, objectFit: "cover", background: "#fafafa" }}
                    />
                  ) : (
                    <div style={{
                      height: 200, display: "flex", alignItems: "center",
                      justifyContent: "center", background: "#fafafa", color: "#bbb",
                    }}>
                      {t.status === "failed" ? "❌ 生成失败" : t.status === "pending" ? "排队中…" : "生成中…"}
                    </div>
                  )
                }
                actions={[
                  t.has_image ? (
                    <a key="dl" href={mediaUrl(`/api/images/${t.id}/file`)} download>
                      <DownloadOutlined />
                    </a>
                  ) : (
                    <span key="none" style={{ color: "#ccc" }}>—</span>
                  ),
                  t.status !== "pending" && t.status !== "running" && (
                    <Popconfirm key="del" title="删除该图片？" onConfirm={() => del(t.id)}>
                      <a style={{ color: "#ff4d4f" }}><DeleteOutlined /></a>
                    </Popconfirm>
                  ),
                ].filter(Boolean)}
              >
                <Card.Meta
                  title={
                    <Space>
                      <Tag color={STATUS[t.status].color}>{STATUS[t.status].label}</Tag>
                      <span style={{ fontSize: 12, color: "#999" }}>{t.size}</span>
                      {t.seed != null && (
                        <span style={{ fontSize: 12, color: "#999" }}>seed {t.seed}</span>
                      )}
                    </Space>
                  }
                  description={
                    <span style={{ display: "block", height: 40, overflow: "hidden", fontSize: 12 }}>
                      {t.prompt.slice(0, 60)}
                      {t.error && <div style={{ color: "#ff4d4f" }}>{t.error.slice(0, 80)}</div>}
                    </span>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
