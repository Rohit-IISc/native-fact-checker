FROM mcr.microsoft.com/devcontainers/python:3.12

RUN apt-get update && apt-get install -y ffmpeg curl gnupg ca-certificates apt-transport-https make \
    libraqm0 fonts-noto-core fonts-noto-ui-core \
 && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list \
 && apt-get update && apt-get install -y google-cloud-cli \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
