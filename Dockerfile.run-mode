FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install git, curl (for Node.js install), and other necessary tools
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 and npm 11
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@11.4.0


# Clean npm cache
RUN npm cache clean --force    

# Install ajv for NPX 
RUN npm install -g ajv supergateway@2.8.3 yargs   

# Log npm and npx versions for verification
RUN echo "npm version: $(npm -v)" && echo "npx version: $(npx --version)"

# Verify installation
RUN node -v && npm -v && npx --version

# Copy the requirements file into the container at /app
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Install the package in editable mode
RUN pip install -e .


# Add entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Default command to run the entrypoint script
CMD ["/app/entrypoint.sh"]
