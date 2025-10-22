# 🚀 MarketLens 快速启动指南

## 一键启动

```bash
# 方式 1: 使用启动脚本
./start.sh

# 方式 2: 手动启动
conda activate marketlens
python manager/agent_stream_gradio.py
```

访问: **http://localhost:7860**

---

## 📋 环境信息

- **环境名称**: `marketlens`
- **Python 版本**: 3.11.14
- **依赖数量**: 130 个包
- **主要模型**: Gemini 2.5 Pro

---

## 🔑 必需配置

在项目根目录创建 `.env` 文件：

```env
GOOGLE_API_KEY=你的_Gemini_API_密钥
```

---

## 📦 核心依赖版本

```
langchain==0.3.27
langchain-google-genai==2.0.9
gradio==5.49.1
fastapi==0.119.1
yfinance==0.2.66
beautifulsoup4==4.14.2
trafilatura==2.0.0
playwright==1.55.0
```

---

## 🛠️ 常用命令

### 激活环境
```bash
conda activate marketlens
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 更新依赖
```bash
pip install --upgrade langchain langchain-google-genai
pip freeze > requirements.txt
```

### 查看已安装包
```bash
pip list
```

### 测试环境
```bash
python -c "from config import LLM_GOOGLE; print('✅ 环境正常')"
```

---

## 🎯 使用示例

启动后，在界面中输入：

```
分析一下 NVDA 的最新情况
```

系统会自动：
1. 📊 收集数据（新闻、基本面、市场、情绪）
2. 🔬 深度研究（多空辩论）
3. 💹 生成交易决策
4. ⚠️ 风险管理分析

---

## 🐛 快速故障排除

### 问题: 无法导入模块
```bash
conda activate marketlens
pip install -r requirements.txt
```

### 问题: API Key 错误
检查 `.env` 文件是否存在且正确：
```bash
cat .env | grep GOOGLE_API_KEY
```

### 问题: Playwright 浏览器未安装
```bash
playwright install chromium
```

---

## 📖 更多文档

- **完整安装指南**: 查看 `SETUP.md`
- **项目说明**: 查看 `README.md`
- **日志系统**: 查看 `manager/LOG_SYSTEM_README.md`

---

## 📊 系统状态检查

```bash
# 检查 Python 版本
python --version  # 应显示 3.11.x

# 检查 Conda 环境
conda env list | grep marketlens  # 应显示 *marketlens

# 检查核心模块
python -c "import langchain, gradio; print('✅ OK')"
```

---

## 💡 提示

- ✅ **推荐**: 使用 `./start.sh` 一键启动
- ✅ **推荐**: 设置 `verbose=True` 查看详细推理过程
- ✅ **推荐**: 定期备份 `database/` 目录的分析结果
- ⚠️ **注意**: 首次运行可能需要下载模型数据

---

## 🆘 需要帮助？

1. 检查 `SETUP.md` 中的详细说明
2. 查看终端输出的错误信息
3. 确认 `.env` 文件配置正确
4. 验证网络连接是否正常

---

**上次更新**: 2025-10-22  
**环境名称**: marketlens  
**状态**: ✅ 已验证可用

