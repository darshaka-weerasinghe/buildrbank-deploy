# ---------------------------------------------------------------
# BuildrBank, in a box.
#
#   docker build -t buildrbank .
#   docker run -d -p 8000:8000 --env-file .env --name bank buildrbank
#
# Then open http://localhost:8000
# ---------------------------------------------------------------

# 3.12, not "latest". On a very new Python some of these libraries have
# no ready-made package yet and pip tries to build them from source -
# it looks like a hang, then fails. Pin the version you tested with.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, in their own layer. Docker reuses this layer every
# time you rebuild after only changing code, which turns a four-minute
# rebuild into a four-second one.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the code. Three folders, listed one by one rather than `COPY . .`
# so nothing unexpected creeps in.
COPY app/ ./app/
COPY vendor/ ./vendor/
COPY scripts/ ./scripts/

# The agent writes its conversation to /app/data, but it never creates
# that folder itself. Without this line the container starts and then
# dies the moment anyone sends a message.
RUN mkdir -p /app/data

# This is documentation, not a door. The port is only reachable because
# of the -p flag on `docker run`.
EXPOSE 8000

# 0.0.0.0, not 127.0.0.1. Inside a container, 127.0.0.1 means "only this
# container" - the outside world could never reach it.
CMD ["uvicorn", "app.api:api", "--host", "0.0.0.0", "--port", "8000"]
