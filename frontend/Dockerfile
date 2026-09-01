# Multi-stage build: stage 1 needs the whole Node toolchain to compile the
# React app; stage 2 ships only the finished static files on a tiny nginx
# image. The toolchain never reaches production.
# Both stages digest-pinned (reproducible builds, no tag poisoning); the tags
# ride along as comments and Dependabot bumps the digests.
FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS build

WORKDIR /app

# Copy the lockfiles first so Docker can cache the npm install layer: it only
# reruns when dependencies change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.31-alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
