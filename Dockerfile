FROM python:3.14-alpine

LABEL org.opencontainers.image.source="https://github.com/tuudik/cloudflare-dns-manager"
LABEL org.opencontainers.image.description="Automated Cloudflare DNS manager with Docker label discovery"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY dns-manager.py .

# Create non-root user for security
RUN addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser && \
    chown -R appuser:appuser /app

USER appuser

CMD ["python", "-u", "dns-manager.py"]
