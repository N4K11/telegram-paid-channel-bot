#!/bin/sh
set -eu

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

python main.py
