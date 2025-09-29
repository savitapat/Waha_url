FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install WAHA using the official method that works on Render
RUN apt-get update && apt-get install -y wget && \
    wget -O waha https://github.com/devlikeapro/waha/releases/latest/download/waha-linux && \
    chmod +x waha

CMD sh -c "./waha & python web_service.py"