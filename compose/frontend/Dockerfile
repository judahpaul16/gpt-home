FROM node:18-alpine AS builder

# Install git for version script and configure safe directory
RUN apk add --no-cache git && \
    git config --global --add safe.directory /app

WORKDIR /app
COPY src/frontend/package*.json ./
RUN npm install

COPY .git ./.git
COPY src/frontend ./
RUN npm run build

# Production: serve static files with nginx
FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html
EXPOSE 3000
