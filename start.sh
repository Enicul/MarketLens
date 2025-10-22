#!/bin/bash

echo "🚀 启动 MarketLens AI 系统..."
echo ""

# 激活conda环境
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate marketlens

# 检查环境变量
if [ ! -f ".env" ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "请创建 .env 文件并添加 GOOGLE_API_KEY"
    exit 1
fi

# 检查 API 密钥
if ! grep -q "GOOGLE_API_KEY" .env; then
    echo "⚠️  警告: .env 文件中未找到 GOOGLE_API_KEY"
fi

echo "✅ 环境检查通过"
echo "📊 启动 Gradio 界面..."
echo "📱 访问地址: http://localhost:7860"
echo ""

# 启动应用
python manager/agent_stream_gradio.py

