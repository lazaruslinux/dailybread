# Multi-stage build: stage 1 needs the whole Node toolchain to compile the
# React app; stage 2 ships only the finished static files on a tiny nginx
# image. The toolchain never reaches production.
# Both stages digest-pinned (reproducible builds, no tag poisoning); the tags
# ride along as comments and Dependabot bumps the digests.
FROM node:26-alpine@sha256:e88a35be04478413b7c71c455cd9865de9b9360e1f43456be5951032d7ac1a66 AS build

WORKDIR /app

# Copy the lockfiles first so Docker can cache the npm install layer: it only
# reruns when dependencies change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
