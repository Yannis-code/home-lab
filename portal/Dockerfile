FROM node:22-alpine AS build

WORKDIR /app
COPY portal-app/package*.json ./
RUN npm ci
COPY portal-app/ ./
RUN npm run build

FROM python:3.13-alpine

WORKDIR /app
COPY --from=build /app/dist/portal-app/browser /app/dist
COPY portal.py /app/portal.py

CMD ["python", "/app/portal.py"]