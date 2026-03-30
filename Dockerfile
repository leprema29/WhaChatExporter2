FROM python:3.12-slim

LABEL maintainer="WhaChatExporter2"
LABEL description="WhatsApp Chat Exporter - Parse WhatsApp databases to HTML/JSON/TXT/CSV/Markdown"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY Whatsapp_Chat_Exporter/ Whatsapp_Chat_Exporter/

# Install the package with all dependencies
RUN pip install --no-cache-dir ".[all]"

# Create a volume for input/output data
VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["wtsexporter"]
CMD ["--help"]
