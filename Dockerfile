# =============================================================================
# Stage 1: Builder
# Has all build tools (gcc, g++, make, etc.) — NOT copied to final image.
# =============================================================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ make \
    libcairo2-dev pkg-config python3-dev \
    libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# ── Critical: install CPU-only PyTorch BEFORE requirements.txt ────────────────
# openai-whisper depends on torch but does not pin a CPU/GPU variant.
# If we let pip resolve it from PyPI it pulls the full CUDA build (~2.4 GB).
# Installing torch from the CPU wheel index first prevents that.
RUN pip install --no-cache-dir \
    torch torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install the rest (torch is already satisfied → pip skips CUDA re-install)
RUN pip install --no-cache-dir -r requirements.txt

# Download Playwright Chromium binary into the builder cache
RUN playwright install chromium

# =============================================================================
# Stage 2: Runtime  (lean — no build tools, no CUDA, no dev headers)
# =============================================================================
FROM python:3.12-slim AS runtime

# Enable non-free repos — fonts-ubuntu lives in non-free on Debian Trixie
RUN sed -i \
    's/^Components: main$/Components: main contrib non-free non-free-firmware/' \
    /etc/apt/sources.list.d/debian.sources

# Runtime system deps only (no gcc/g++/make/libcairo2-dev/pkg-config)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Media
    ffmpeg \
    # Shared libs needed by Python packages at runtime
    libcairo2 \
    libpq5 \
    # Chromium / Playwright runtime deps
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    # Fonts — verified available in Debian Trixie
    fonts-dejavu-core \
    fonts-liberation \
    fonts-freefont-ttf \
    fonts-ubuntu \
    # Node.js (needed for hyperframes)
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Copy Python environment from builder ────────────────────────────────────
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# ── Copy Playwright Chromium binary from builder ─────────────────────────────
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

WORKDIR /app

# Install hyperframes CLI globally
RUN npm install -g hyperframes

# Copy project source
COPY . .

EXPOSE 8000
