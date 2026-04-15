# Open WebUI With The Local Server

This repo's local OpenAI-compatible endpoint is:

```text
http://127.0.0.1:8001/v1
```

That is the correct base URL from the host machine.

For an Open WebUI Docker container, `localhost` inside the container points back to the container itself, not the host. Use:

```text
http://host.docker.internal:8001/v1
```

## Run the local server

Start the local model server first so it is listening on port `8001`.

The launcher defaults in this repo already use port `8001`, so a typical local run is:

```bash
./run-server.py
```

## Run Open WebUI in Docker

```bash
docker run -d \
  --name open-webui \
  --restart always \
  -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8001/v1 \
  -e OPENAI_API_KEY=dummy \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

Then open:

```text
http://localhost:3000
```

## If the container already exists

If Open WebUI is already running with the wrong backend URL, recreate it with the updated `OPENAI_API_BASE_URL`.

Check the current setting:

```bash
docker inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' | rg '^OPENAI_API_BASE_URL='
```

If it still points at `8000`, remove and recreate the container:

```bash
docker rm -f open-webui
docker run -d \
  --name open-webui \
  --restart always \
  -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8001/v1 \
  -e OPENAI_API_KEY=dummy \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

The named volume `open-webui` preserves users, settings, and chat history across container recreation.

## Notes

- Host-side tools can use `http://127.0.0.1:8001/v1` or `http://localhost:8001/v1`.
- Dockerized Open WebUI should use `http://host.docker.internal:8001/v1`.
- `OPENAI_API_KEY=dummy` is sufficient when the local wrapper accepts any placeholder key.
