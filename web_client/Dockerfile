FROM node:20-alpine AS builder

WORKDIR /app

ARG NODE_OPTIONS=--max_old_space_size=512
ENV NODE_OPTIONS=${NODE_OPTIONS}

COPY package*.json ./
RUN npm install

COPY . .
RUN GENERATE_SOURCEMAP=false REACT_APP_API_BASE_URL=https://richclub.efforthye.dev npm run build

FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
