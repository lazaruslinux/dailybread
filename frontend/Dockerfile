# Multi-stage build: stage 1 needs the whole Node toolchain to compile the
# React app; stage 2 ships only the finished static files on a tiny nginx
# image. The toolchain never reaches production.
FROM node:26-alpine AS build

WORKDIR /app

# Copy the lockfiles first so Docker can cache the npm install layer: it only
# reruns when dependencies change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
