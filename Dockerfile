FROM python:3.9-slim

# Install dependencies
RUN apt-get update && apt-get install -y curl

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy your app
COPY app.py .

# Download and setup WAHA
RUN curl -L https://github.com/devlikeapro/waha/releases/latest/download/waha-linux -o waha
RUN chmod +x waha

# Expose ports
EXPOSE 3000 5000

# Start both services
CMD sh -c "./waha & python app.py"