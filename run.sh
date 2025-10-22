docker network create \
  --driver=bridge \
  --subnet=172.28.0.0/16 \
  --gateway=172.28.0.1 \
  --opt com.docker.network.bridge.name=br-proxy \
  proxy
docker compose up -d