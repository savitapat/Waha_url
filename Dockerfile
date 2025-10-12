FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Download WAHA
RUN wget -O /usr/local/bin/waha https://github.com/devlikeapro/waha/releases/download/v5.0.0/waha-linux-x64-5.0.0
RUN chmod +x /usr/local/bin/waha

# Copy your app
COPY render_app.py .
COPY start.sh .

# Start both services
CMD ["bash", "start.sh"]
