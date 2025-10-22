# MarketLens 环境安装指南

## 📦 全新环境安装

### 1. 创建 Conda 环境

```bash
conda create -n marketlens python=3.11 -y
conda activate marketlens
```

### 2. 安装依赖包

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# Gemini API Key (主要使用)
GOOGLE_API_KEY=你的_Gemini_API_密钥

# OpenAI API Key (可选，用于切换模型)
OPENAI_API_KEY=你的_OpenAI_API_密钥
```

### 4. 安装 Playwright 浏览器（如需使用）

```bash
playwright install
```

---

## 🎯 获取 API 密钥

### Gemini API Key
1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 登录 Google 账号
3. 点击 "Get API Key" 或 "Create API Key"
4. 复制生成的密钥到 `.env` 文件

### OpenAI API Key（可选）
1. 访问 [OpenAI Platform](https://platform.openai.com/api-keys)
2. 创建新的 API Key
3. 复制到 `.env` 文件

---

## 🚀 运行应用

### Gradio 界面（推荐）
```bash
python manager/agent_stream_gradio.py
```

访问: http://localhost:7860

### FastAPI 服务器
```bash
python manager/server/main.py
```

访问: http://localhost:8000

---

## 📋 核心依赖说明

| 包名 | 版本 | 用途 |
|------|------|------|
| `langchain` | 0.3.27 | LLM 应用框架 |
| `langchain-google-genai` | 2.0.9 | Gemini 模型集成 |
| `langchain-openai` | 0.3.33 | OpenAI 模型集成 |
| `gradio` | 5.49.1 | Web UI 界面 |
| `fastapi` | 0.119.1 | API 服务器 |
| `yfinance` | 0.2.66 | 金融数据获取 |
| `beautifulsoup4` | 4.14.2 | HTML 解析 |
| `trafilatura` | 2.0.0 | 网页内容提取 |
| `playwright` | 1.55.0 | 浏览器自动化 |

---

## 🔧 配置说明

### LLM 模型切换

编辑 `config.py`:

```python
# 使用 Gemini (默认)
LLM_GOOGLE = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",  # 或 gemini-1.5-pro, gemini-2.0-flash-exp
    temperature=0.3,
    google_api_key=google_api_key,
    convert_system_message_to_human=False
)

# 切换到 OpenAI
# 在 agent_stream_gradio.py 中取消注释 OpenAI 相关代码
```

### Verbose 模式（查看推理过程）

编辑 `manager/agent_stream_gradio.py`:

```python
return AgentExecutor(
    ...
    verbose=True,  # 改为 True 查看详细推理过程
    ...
)
```

---

## 🐛 常见问题

### 问题 1: `ModuleNotFoundError: No module named 'dotenv'`
```bash
pip install python-dotenv
```

### 问题 2: `GOOGLE_API_KEY is not set`
确保 `.env` 文件在项目根目录，并包含正确的 API 密钥。

### 问题 3: Playwright 浏览器未安装
```bash
playwright install chromium
```

### 问题 4: 版本冲突
删除环境重新创建：
```bash
conda deactivate
conda env remove -n marketlens
conda create -n marketlens python=3.11 -y
conda activate marketlens
pip install -r requirements.txt
```

---

## 📊 系统要求

- **Python**: 3.11
- **操作系统**: macOS / Linux / Windows
- **内存**: 建议 8GB+
- **磁盘**: 至少 2GB 可用空间

---

## ✅ 验证安装

运行测试脚本验证环境：

```bash
python -c "
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_google_genai import ChatGoogleGenerativeAI
import gradio
print('✅ 所有核心模块安装成功!')
print(f'Gradio 版本: {gradio.__version__}')
"
```

---

## 📝 更新依赖

如需更新某个包：

```bash
pip install --upgrade 包名
pip freeze > requirements.txt
```

---

## 🆘 获取帮助

- **GitHub Issues**: [项目地址]
- **文档**: 查看 `README.md`
- **日志**: 检查 `manager/LOG_SYSTEM_README.md`

