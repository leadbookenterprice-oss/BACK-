FROM python:3.12-slim

# Install system dependencies (C++, Node.js repo, and Chrome for Puppeteer)
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    make \
    ffmpeg \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libpq-dev \
    git \
    # Chromium / Playwright dependencies
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
    # Fonts — Debian Trixie renamed these packages
    fonts-ubuntu \
    fonts-unifont \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Copy project files
COPY . .

# Install hyperframes globally
RUN npm install -g hyperframes

# Expose port
EXPOSE 8000
