// 创作页：文生视频 / 图生视频 / 分镜 三种模式
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  message,
  Select,
  Space,

  Tabs,
  Tag,

} from "antd";
import { PictureOutlined, SendOutlined, ThunderboltFilled } from "@ant-design/icons";
import { api } from "../api";
import type { OptimizeResult, ProviderInfo } from "../api";
import { useAuth } from "../auth";
import { ShotEditor } from "../components/ShotEditor";

export default function Create() {
  return (
    <Tabs
      defaultActiveKey="single"
      centered
      items={[
        { key: "single", label: "🎬 单镜头生成", children: <SingleMode /> },
        { key: "storyboard", label: "🎞️ 分镜脚本", children: <StoryboardMode /> },
      ]}
    />
  );
}

/* ============ 单镜头模式：t2v / i2v + 多候选 ============ */
function SingleMode() {
  const { user, refresh } = useAuth();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [provider, setProvider] = useState("");
  const [prompt, setPrompt] = useState("");
  const [optimized, setOptimized] = useState<OptimizeResult | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [taskType, setTaskType] = useState<"t2v" | "i2v">("t2v");
  const [imageId, setImageId] = useState<string | null>(null);
  const [imageName, setImageName] = useState("");
  const [duration, setDuration] = useState(5);
  const [ratio, setRatio] = useState("16:9");
  const [candidates, setCandidates] = useState(1);
  const [autoOptimize, setAutoOptimize] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get<ProviderInfo[]>("/api/tasks/providers").then((ps) => {
      setProviders(ps);
      if (ps.length) setProvider(ps[0].name);
      else message.warning("后端未配置任何生成引擎，请在 .env 中填写 API Key");
    });
  }, []);

  const doOptimize = async () => {
    if (!prompt.trim()) return message.warning("请先输入描述");
    setOptimizing(true);
    try {
      setOptimized(await api.post<OptimizeResult>("/api/tasks/optimize", { prompt }));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "优化失败");
    } finally {
      setOptimizing(false);
    }
  };

  const uploadImage = async (file: File) => {
    try {
      const res = await api.upload<{ image_id: string }>("/api/tasks/upload-image", file);
      setImageId(res.image_id);
      setImageName(file.name);
      setTaskType("i2v");
      message.success("参考图已上传");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "上传失败");
    }
  };

  const submit = async () => {
    if (!prompt.trim()) return message.warning("请输入描述");
    if (taskType === "i2v" && !imageId) return message.warning("图生视频需要先上传参考图");
    if (duration > 10 && taskType === "i2v") return message.warning("长视频模式暂不支持参考图，请移除参考图或选 10 秒以内");
    setSubmitting(true);
    try {
      const res = duration > 10
        ? await api.post<{ message: string }>("/api/tasks", {
            prompt,
            provider,
            task_type: "t2v",
            duration: 10,
            aspect_ratio: ratio,
            optimize: autoOptimize,
            candidates: 1,
            total_duration: duration,
          })
        : await api.post<{ message?: string }>("/api/tasks", {
            prompt,
            provider,
            task_type: taskType,
            duration,
            aspect_ratio: ratio,
            optimize: autoOptimize,
            candidates,
            image_id: imageId,
          });
      message.success(res.message ?? `已提交${candidates > 1 ? ` ${candidates} 个候选任务` : "生成任务"}，请到任务历史查看`);
      await refresh();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      {providers.length === 0 && (
        <Alert
          type="warning"
          showIcon
          message="未检测到可用的生成引擎"
          description="请在后端 .env 中配置 VOLCENGINE_API_KEY 或 ZHIPU_API_KEY 后重启服务"
          style={{ marginBottom: 16 }}
        />
      )}
      <Card>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          {/* 参考图上传 */}
          <div>
            <Space>
              <Button
                icon={<PictureOutlined />}
                onClick={() => fileRef.current?.click()}
                type={taskType === "i2v" ? "primary" : "default"}
              >
                {imageId ? "重新上传参考图" : "上传参考图（图生视频）"}
              </Button>
              {imageId && (
                <Tag closable onClose={() => { setImageId(null); setTaskType("t2v"); }}>
                  {imageName}
                </Tag>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadImage(f);
                  e.target.value = "";
                }}
              />
            </Space>
          </div>

          {/* 描述输入 */}
          <Input.TextArea
            rows={3}
            placeholder="描述你想要的画面，例如：一只橘猫在雪地里追蝴蝶，午后阳光……（口语即可，系统会自动优化为专业提示词）"
            value={prompt}
            onChange={(e) => { setPrompt(e.target.value); setOptimized(null); }}
            maxLength={2000}
            showCount
          />

          {/* 提示词优化 */}
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

          {/* 参数 */}
          <Space wrap size={16}>
            <span>引擎：</span>
            <Select
              style={{ width: 200 }}
              value={provider}
              onChange={setProvider}
              options={providers.map((p) => ({ value: p.name, label: p.label }))}
              placeholder="选择引擎"
            />
            <span>时长：</span>
            <Select style={{ width: 130 }} value={duration} onChange={setDuration} options={[
              { value: 5, label: "5 秒" },
              { value: 10, label: "10 秒" },
              { value: 15, label: "15 秒 · 分镜" },
              { value: 20, label: "20 秒 · 分镜" },
              { value: 30, label: "30 秒 · 分镜" },
              { value: 60, label: "60 秒 · 分镜" },
            ]} />
            {duration > 10 && (
              <span style={{ color: "#faad14", fontSize: 12 }}>
                长视频：AI 自动拆分镜头并行生成，完成后自动拼接成片
              </span>
            )}
            <span>比例：</span>
            <Select style={{ width: 100 }} value={ratio} onChange={setRatio} options={[
              { value: "16:9", label: "16:9 横屏" },
              { value: "9:16", label: "9:16 竖屏" },
            ]} />
            <span>候选数：</span>
            <Select style={{ width: 130 }} value={candidates} onChange={setCandidates} options={[
              { value: 1, label: "1 个（省配额）" },
              { value: 2, label: "2 个候选" },
              { value: 3, label: "3 个候选" },
              { value: 4, label: "4 个候选" },
            ]} />
          </Space>

          <div style={{ textAlign: "right", color: "#999" }}>
            {user?.quota_enabled === false
              ? "生成次数：无限制"
              : `今日已用 ${user?.quota_used_today ?? 0} / ${user?.daily_quota ?? 0}`}
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
            开始生成{duration > 10 ? `（${duration}秒长视频·自动分镜）` : candidates > 1 ? `（${candidates}个候选）` : ""}
          </Button>
        </Space>
      </Card>
    </div>
  );
}

/* ============ 分镜模式 ============ */
function StoryboardMode() {
  return <ShotEditor />;
}
