FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY omniprox/ ./omniprox/
COPY omniprox.py .
COPY omni .

# Make scripts executable
RUN chmod +x omni omniprox.py

# Create config directory
RUN mkdir -p /root/.omniprox

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app:${PATH}"

# Default command
ENTRYPOINT ["python", "omniprox.py"]
CMD ["--help"]