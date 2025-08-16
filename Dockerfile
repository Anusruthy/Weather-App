# Use an official lightweight Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory inside container
WORKDIR /app

# Install system dependencies (for geopy)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching layers)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files into the container
COPY . .

# Expose port (Flask default is 5000)
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
