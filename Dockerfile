# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables for Python and Pipeline paths
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIPELINE_INPUT_DIR=/app/input/target \
    PIPELINE_OUTPUT_DIR=/app/output

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy the application code, models, and inputs
COPY . /app/

# Ensure output and logs directories exist
RUN mkdir -p /app/output /app/logs

# Run the pipeline by default when the container launches
CMD ["python", "main_detector.py"]
