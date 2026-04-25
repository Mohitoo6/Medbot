FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if required by pymupdf / chromadb
RUN apt-get update && apt-get install -y build-essential

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose the default Hugging Face Spaces port
EXPOSE 7860

# Run the Flask app
CMD ["python", "app.py"]
