# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite bakes VITE_* vars into the built JS at build time, not read at runtime,
# so the API's address has to be known here rather than passed to the container later.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS serve
COPY --from=build /srv/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
