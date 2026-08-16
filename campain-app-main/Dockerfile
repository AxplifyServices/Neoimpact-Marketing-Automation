FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=https://marketing-automation-api.axplitest.com/api
ARG VITE_AUTH_URL=https://marketing-automation-api.axplitest.com/api
ARG VITE_API_TIMEOUT=30000
ARG VITE_ENABLE_MOCK_DATA=false

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_AUTH_URL=${VITE_AUTH_URL}
ENV VITE_API_TIMEOUT=${VITE_API_TIMEOUT}
ENV VITE_ENABLE_MOCK_DATA=${VITE_ENABLE_MOCK_DATA}

RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
