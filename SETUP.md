# MarketLens Environment Installation Guide

## 📦 Fresh Environment Installation

### 1. Create Conda Environment

```bash
conda create -n marketlens python=3.11 -y
conda activate marketlens
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create `.env` file in project root:

```bash
# Gemini API Key (primary use)
GOOGLE_API_KEY=your_Gemini_API_key

# OpenAI API Key (optional, for model switching)
OPENAI_API_KEY=your_OpenAI_API_key
```

### 4. Install Playwright Browser (if needed)

```bash
playwright install
```

---

## 🎯 Get API Keys

### Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Log in with Google account
3. Click "Get API Key" or "Create API Key"
4. Copy the generated key to `.env` file

### OpenAI API Key (Optional)
1. Visit [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create new API Key
3. Copy to `.env` file

---

## 🚀 Run Application

### Gradio Interface (Recommended)
```bash
python manager/agent_stream_gradio.py
```

Visit: http://localhost:7860

### FastAPI Server
```bash
python manager/server/main.py
```

Visit: http://localhost:8000

---

## 📋 Core Dependencies

| Package | Version | Purpose |
|------|------|------|
| `langchain` | 0.3.27 | LLM application framework |
| `langchain-google-genai` | 2.0.9 | Gemini model integration |
| `langchain-openai` | 0.3.33 | OpenAI model integration |
| `gradio` | 5.49.1 | Web UI interface |
| `fastapi` | 0.119.1 | API server |
| `yfinance` | 0.2.66 | Financial data retrieval |
| `beautifulsoup4` | 4.14.2 | HTML parsing |
| `trafilatura` | 2.0.0 | Web content extraction |
| `playwright` | 1.55.0 | Browser automation |

---

## 🔧 Configuration

### LLM Model Switching

Edit `config.py`:

```python
# Use Gemini (default)
LLM_GOOGLE = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",  # or gemini-1.5-pro, gemini-2.0-flash-exp
    temperature=0.3,
    google_api_key=google_api_key,
    convert_system_message_to_human=False
)

# Switch to OpenAI
# Uncomment OpenAI related code in agent_stream_gradio.py
```

### Verbose Mode (View Reasoning Process)

Edit `manager/agent_stream_gradio.py`:

```python
return AgentExecutor(
    ...
    verbose=True,  # Change to True to view detailed reasoning process
    ...
)
```

---

## 🐛 Common Issues

### Issue 1: `ModuleNotFoundError: No module named 'dotenv'`
```bash
pip install python-dotenv
```

### Issue 2: `GOOGLE_API_KEY is not set`
Ensure `.env` file is in project root and contains correct API key.

### Issue 3: Playwright browser not installed
```bash
playwright install chromium
```

### Issue 4: Version conflicts
Delete environment and recreate:
```bash
conda deactivate
conda env remove -n marketlens
conda create -n marketlens python=3.11 -y
conda activate marketlens
pip install -r requirements.txt
```

---

## 📊 System Requirements

- **Python**: 3.11
- **OS**: macOS / Linux / Windows
- **Memory**: 8GB+ recommended
- **Disk**: At least 2GB available space

---

## ✅ Verify Installation

Run test script to verify environment:

```bash
python -c "
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_google_genai import ChatGoogleGenerativeAI
import gradio
print('✅ All core modules installed successfully!')
print(f'Gradio version: {gradio.__version__}')
"
```

---

## 📝 Update Dependencies

To update a package:

```bash
pip install --upgrade package_name
pip freeze > requirements.txt
```

---

## 🆘 Get Help

- **GitHub Issues**: [Project URL]
- **Documentation**: Check `README.md`
- **Logs**: Check `manager/LOG_SYSTEM_README.md`
