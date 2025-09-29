FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download and setup WAHA
RUN curl -L https://github.com/devlikeapro/waha/releases/latest/download/waha-linux -o waha
RUN chmod +x waha

# Expose ports for WAHA (3000) and Flask (5000)
EXPOSE 3000 5000

# Start both WAHA and Flask forwarder
CMD sh -c "./waha & python web_service.py"