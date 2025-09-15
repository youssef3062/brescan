# Use official Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Expose the port that the host will map
EXPOSE 8080

# Run the Flask app with Gunicorn (production server)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
