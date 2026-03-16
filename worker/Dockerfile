# Multi-stage: Rust builder + Python runtime
FROM rust:1.82-slim AS rust-builder
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --features subprocess-executor
# Output: /build/target/release/devsper-worker

FROM python:3.12-slim AS final
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 curl && rm -rf /var/lib/apt/lists/*
COPY --from=rust-builder /build/target/release/devsper-worker /usr/local/bin/
RUN pip install --no-cache-dir devsper
ENV DEVSPER_LOG_FORMAT=json
ENV DEVSPER_NODE_ROLE=worker
EXPOSE 7700
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f "http://localhost:${DEVSPER_RPC_PORT:-7700}/health" || exit 1
ENTRYPOINT ["devsper-worker"]
