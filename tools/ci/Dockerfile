FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp DEFAULT_DEVICE=""
WORKDIR /opt/ghost
COPY . /opt/ghost
RUN python3 -m pip install --no-cache-dir . bandit
WORKDIR /workspace
ENTRYPOINT []
