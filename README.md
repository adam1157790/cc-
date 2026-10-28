# 🎬 文生视频创作平台

一个前后端完备的文生视频应用：多引擎云端生成 + 提示词智能优化 + 图生视频 + 多镜头分镜拼接 + 多候选并行 + 用户配额管理。

## 功能一览

| 功能 | 说明 |
|---|---|
| 单镜头生成 | 文生视频 / 图生视频（参考图作首帧），5/10秒，16:9/9:16 |
| 文生图 | 独立模块：火山 Seedream 4.0 / 智谱 CogView-4，独立配额；AI 提示词扩写 + 固定 Seed 精确复现 + 提示词遵循度 + 多候选 |
| 提示词智能优化 | LLM 将口语描述扩写为结构化专业提示词（主体/镜头/光线/风格+负面词），生成前可预览 |
| 多候选并行 | 同一提示词生成最多4个候选，挑选最佳，提高一次满意率 |
| 分镜脚本 | 最多20镜头，逐镜头独立提示词+时长，全部成功后 ffmpeg 自动拼接成片 |
| 任务队列 | 进程内异步 worker，并发上限可配，重启自动恢复未完成任务 |
| 用户系统 | JWT 登录注册，每日配额限制；第一个注册用户自动成为管理员 |
| 管理后台 | 用户/配额/管理员管理、全局任务统计、7日生成量图表 |
| 生成引擎 | 可插拔 Provider：火山引擎 Seedance / 智谱 CogVideoX（配置哪家 Key 用哪家） |

## 快速开始

```bash
# 1. 后端
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # 填入 API Key（见下）
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 2. 前端
cd frontend
npm install
npm run dev               # http://localhost:5173
```

## API Key 配置（backend/.env）

至少配置一家生成引擎 + 一个 LLM（提示词优化）：

- **火山引擎方舟**（推荐）：`VOLCENGINE_API_KEY` — [控制台](https://console.volcengine.com/ark)，开通 Seedance 模型
- **智谱**：`ZHIPU_API_KEY` — [开放平台](https://open.bigmodel.cn)
- **LLM**：`LLM_API_KEY` + `LLM_BASE_URL`（默认方舟 v3，OpenAI 兼容接口均可）

其他：
- `SECRET_KEY` 换成随机字符串（对外提供服务务必修改）
- `ALLOW_REGISTRATION=false` 可关闭注册
- `DEFAULT_DAILY_QUOTA` 新用户每日任务数（管理员可按用户调整）
- `MAX_CONCURRENT_TASKS` 并行生成上限（云端按量计费，注意成本）

## 架构

```
frontend (React18 + Vite + TS + AntD)
   │  REST + JWT
backend (FastAPI + SQLAlchemy async + SQLite)
   ├─ routers/     auth / tasks / storyboards / images(文生图) / admin
   ├─ services/    worker(视频队列) / image_worker(图像队列) / prompt_optimizer / image_prompt_optimizer / video_utils(ffmpeg)
   └─ providers/   可插拔引擎抽象：volcengine / zhipu / (mock 测试)；图像另有 volcengine_image / zhipu_image / mock_image
data/  SQLite库 + videos/ + covers/ + images/ + uploads/
```

「精确度」的三层保障：① LLM 提示词结构化扩写 ② 参考图控制首帧 ③ 多候选择优；分镜模式再叠加镜头级控制与 ffmpeg 统一转码拼接。文生图的精确输出：AI 结构化扩写（严格保留数量/文字/颜色等精确要求）+ 固定 Seed 复现 + 提示词遵循度（guidance）+ 多候选。

## 测试

`ENABLE_MOCK_PROVIDER=1` 环境变量下启动后端可注册一个假引擎（返回示例视频），用于无 Key 冒烟测试全流程：

```bash
cd backend
set ENABLE_MOCK_PROVIDER=1
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

前端 API 地址默认 `http://localhost:8000`，如部署到别处，在 `frontend/.env` 写 `VITE_API_BASE=https://你的后端地址` 后重新构建。

也可一键启动：双击项目根目录 `start.bat`（自动开两个窗口跑前后端并打开浏览器）。

## 已知注意事项

- 云端厂商返回的视频 URL 有效期短（方舟24h），系统会立即下载落盘到 `data/videos/`，不受影响
- Windows 中文环境下 ffmpeg 子进程已按 UTF-8 解码处理，无需手动安装 ffmpeg（imageio-ffmpeg 自带）
- 本机 SQLAlchemy 2.1.6 的 Cython 扩展在 Python 3.14 + Windows 下 DLL 加载失败，安装后如遇 ImportError 请删除 `.venv/Lib/site-packages/sqlalchemy/**/*_cy*.pyd`，纯 Python 回退运行无功能差异
