#!/bin/bash
# Bootstrap script for Linux/macOS
# Checks for 'uv' and launches setup_project.py

if ! command -v uv &> /dev/null
then
    echo "[ERROR] 'uv' is not installed or not in your PATH."
    echo ""
    echo "Please install uv first by running:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "Then restart your terminal and run this script again."
    exit 1
fi

echo "[BOOTSTRAP] Found uv. Launching setup..."
uv run setup_project.py
