# Build context: repo root (.)
# Dockerfile path: apps/rust-svc/Dockerfile

# Stage 1: build
FROM rust:1.82-slim AS builder
WORKDIR /workspace

# Copy workspace Cargo files; create stubs for sibling crates so cargo can
# resolve the full workspace dependency graph without compiling them.
COPY Cargo.toml Cargo.lock* ./
COPY apps/rust-svc/Cargo.toml ./apps/rust-svc/
COPY packages/py-core/Cargo.toml ./packages/py-core/
COPY packages/wasm-core/Cargo.toml ./packages/wasm-core/

RUN mkdir -p apps/rust-svc/src packages/py-core/src packages/wasm-core/src && \
    echo "fn main() {}" > apps/rust-svc/src/main.rs && \
    touch packages/py-core/src/lib.rs packages/wasm-core/src/lib.rs && \
    cargo build --release -p rust-svc && \
    rm -rf apps/rust-svc/src

# Copy real source and rebuild (only rust-svc recompiles; deps are cached)
COPY apps/rust-svc/src ./apps/rust-svc/src
RUN touch apps/rust-svc/src/main.rs && \
    cargo build --release -p rust-svc

# Stage 2: minimal runtime image
FROM debian:bookworm-slim AS runner
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

COPY --from=builder /workspace/target/release/rust-svc /usr/local/bin/rust-svc

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["/usr/local/bin/rust-svc"]
