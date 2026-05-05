FROM python:3.12-slim

# Enable non-free repos (needed for fonts-ubuntu which is non-free in Debian Trixie)
RUN sed -i 's/^Components: main$/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources

# Install system dependencies
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
    # Chromium / Playwright runtime dependencies
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
    # Fonts (verified available in Debian Trixie)
    fonts-dejavu-core \
    fonts-liberation \
    fonts-freefont-ttf \
    fonts-ubuntu \
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
