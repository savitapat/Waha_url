FROM python:3.11-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# add cloudflared binary
ADD https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 /usr/local/bin/cloudflared
RUN chmod +x /usr/local/bin/cloudflared

# make sure start.sh is executable
RUN chmod +x /app/start.sh

EXPOSE 5000

CMD ["/app/start.sh"]
