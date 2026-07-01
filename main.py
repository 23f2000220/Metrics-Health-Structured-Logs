import time
import uuid
import json
import collections

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from prometheus_client import Counter, CONTENT_TYPE_LATEST, generate_latest

START_TIME = time.time()
EMAIL = "23f2000220@ds.study.iitm.ac.in"

REQUEST_COUNTER = Counter("http_requests_total", "Total HTTP requests", ["path", "method"])

LOG_BUFFER = collections.deque(maxlen=2000)

# Pre-touch a label combo so the metric series exists even before any traffic.
REQUEST_COUNTER.labels(path="/healthz", method="GET")

app = FastAPI()


def log_event(level, path, request_id, **extra):
    entry = {
        "level": level,
        "ts": time.time(),
        "path": path,
        "request_id": request_id,
    }
    entry.update(extra)
    LOG_BUFFER.append(entry)
    print(json.dumps(entry))


@app.middleware("http")
async def instrument(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Increment BEFORE handling the request so /metrics always reflects
    # the current request too, and so a first-ever /metrics call isn't empty.
    REQUEST_COUNTER.labels(path=request.url.path, method=request.method).inc()

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    log_event(
        "info",
        request.url.path,
        request_id,
        method=request.method,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 3),
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/work")
async def work(request: Request, n: int = 1):
    # do K units of "work"
    total = 0
    for i in range(max(0, n)):
        total += i * i
    return {"email": EMAIL, "done": n}


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "uptime_s": max(0.0, time.time() - START_TIME)}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/tail")
async def logs_tail(limit: int = 50):
    limit = max(1, min(limit, len(LOG_BUFFER) if LOG_BUFFER else 1))
    items = list(LOG_BUFFER)[-limit:]
    return JSONResponse(content=items)
