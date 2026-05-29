#!/bin/bash
# Arranca Streamlit app
# Uso: ./run_app.sh

echo "Starting Carbon Farming Tracker..."
echo "URL: http://localhost:8501"
echo ""

cd "$(dirname "$0")"
streamlit run streamlit_app/app.py \
    --server.port 8501 \
    --server.headless true \
    --theme.primaryColor "#2d6a4f" \
    --theme.backgroundColor "#ffffff" \
    --theme.secondaryBackgroundColor "#f0f7f0"
