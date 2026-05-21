# 字幕翻译 Web 服务

基于 FastAPI + React 的字幕翻译服务，支持通过 Cloudflare Tunnel 暴露到公网供小白同事使用。

## 快速启动

### 一键启动（推荐）

```powershell
cd subtitle-web
.\start.ps1
```

### 手动启动

#### 1. 安装后端依赖

```powershell
cd subtitle-web/backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```powershell
cd subtitle-web/backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 启动前端开发服务器

```powershell
cd subtitle-web/frontend
pnpm dev
```

### 4. 访问服务

- 前端地址: http://localhost:5173
- 后端 API 文档: http://localhost:8000/docs

## Cloudflare Tunnel 部署

### 1. 安装 cloudflared

下载并安装 cloudflared 到您的系统。

### 2. 创建 Cloudflare Tunnel

```powershell
cloudflared tunnel create <隧道名称>
```

### 3. 配置 DNS

在 Cloudflare Dashboard 中为您的域名添加 CNAME 记录指向隧道。

### 4. 运行隧道

```powershell
cloudflared tunnel run <隧道名称>
```

## 项目结构

```
subtitle-web/
├── backend/              # FastAPI 后端
│   ├── main.py          # 应用入口
│   ├── models.py        # Pydantic 数据模型
│   ├── tasks.py         # 任务管理
│   ├── requirements.txt # Python 依赖
│   └── routes/          # API 路由
│       ├── translate.py  # 翻译相关 API
│       └── presets.py    # 预设管理 API
│
├── frontend/            # React 前端
│   ├── src/
│   │   ├── components/  # UI 组件
│   │   ├── hooks/       # React Hooks
│   │   ├── services/    # API 服务
│   │   └── App.tsx      # 主应用
│   ├── tailwind.config.js # Tailwind 配置（Apple Design）
│   └── dist/           # 构建产物
│
└── uploads/            # 上传文件目录（自动创建）
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/translate | 提交翻译任务 |
| GET | /api/tasks/{task_id} | 查询任务状态 |
| GET | /api/tasks/{task_id}/download | 下载翻译结果 |
| GET | /api/tasks/{task_id}/logs | 获取任务日志 |
| GET | /api/presets | 获取预设列表 |
| POST | /api/presets | 保存新预设 |
| GET | /api/config | 获取当前配置 |

## 技术栈

- **后端**: FastAPI + Python 3
- **前端**: React 18 + TypeScript + Tailwind CSS v3
- **构建工具**: Vite
- **包管理**: pnpm
