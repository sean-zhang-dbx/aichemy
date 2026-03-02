FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src/ ./src/
COPY public/ ./public/
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=frontend /app/dist ./dist
COPY server/ ./server/
COPY config.yml tools.txt ./
COPY skills/ ./skills/
EXPOSE 8000
CMD ["python", "server/server.py"]
