#!/bin/bash

echo "🚀 Launching the MarketLens AI system..."
echo ""

# Activate the conda environment
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate marketlens

# Check environment variables
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file does not exist"
    echo "Please create a .env file and add GOOGLE_API_KEY"
    exit 1
fi

# Check API key
if ! grep -q "GOOGLE_API_KEY" .env; then
    echo "⚠️  Warning: GOOGLE_API_KEY not found in .env file"
fi

echo "✅ Environment check passed"
echo "📊 Starting Gradio interface..."
echo "📱 Access at: http://localhost:7860"
echo ""

# Launch application
python manager/agent_stream_gradio.py
