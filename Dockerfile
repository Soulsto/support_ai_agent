# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir keeps the image size smaller
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY src/ ./src
COPY app/ ./app
COPY assets/ ./assets
COPY data/ ./data
COPY backend/ ./backend
COPY scripts/ ./scripts

# Let Docker know that the container listens on this port
EXPOSE 8501

# The command to run your Streamlit app
# --server.address=0.0.0.0 allows it to be accessed from outside the container
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]