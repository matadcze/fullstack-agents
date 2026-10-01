#!/usr/bin/env python3
"""Check that rust-svc is opt-in in every supported Compose configuration."""

import atexit
import json
import os
import subprocess
from pathlib import Path


DEFAULT_SERVICES = {
    "api",
    "celery-beat",
    "celery-worker",
    "grafana",
    "nginx",
    "pgadmin",
    "postgres",
    "prometheus",
    "redis",
    "web",
}
PRODUCTION_SERVICES = {
    "api",
    "celery-beat",
    "celery-worker",
    "nginx",
    "postgres",
    "redis",
    "web",
}

created_env_files = []
for env_file in ("apps/api/.env", "apps/web/.env"):
    try:
        descriptor = os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        continue
    os.close(descriptor)
    created_env_files.append(Path(env_file))


def remove_created_env_files():
    for env_file in created_env_files:
        env_file.unlink(missing_ok=True)


atexit.register(remove_created_env_files)


def compose(*args):
    return subprocess.run(
        ["docker", "compose", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def check_services(label, expected, *compose_args):
    actual = set(compose(*compose_args, "config", "--services").splitlines())
    if actual != expected:
        raise AssertionError(
            f"{label} services differ: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def rust_config(*compose_args):
    rendered = compose(
        "--profile",
        "rust",
        *compose_args,
        "config",
        "--no-env-resolution",
        "--format",
        "json",
    )
    return json.loads(rendered)["services"]["rust-svc"]


def check_rust_configuration(label, service, expect_host_port):
    ports = service.get("ports", [])
    expected_ports = [
        {
            "mode": "ingress",
            "target": 8080,
            "published": "8080",
            "protocol": "tcp",
        }
    ] if expect_host_port else []
    if ports != expected_ports:
        raise AssertionError(f"{label} Rust ports differ: {ports!r}")

    expected_healthcheck = {
        "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
        "timeout": "10s",
        "interval": "30s",
        "retries": 3,
        "start_period": "10s",
    }
    if service["healthcheck"] != expected_healthcheck:
        raise AssertionError(
            f"{label} Rust health check changed: {service['healthcheck']!r}"
        )
    if service["restart"] != "unless-stopped":
        raise AssertionError(f"{label} Rust restart policy changed")
    if service["profiles"] != ["rust"]:
        raise AssertionError(f"{label} Rust profile missing: {service['profiles']!r}")


base = ("-f", "docker-compose.yml")
development = (*base, "-f", "docker-compose.override.yml")
production = ("-f", "docker-compose.prod.yml")

check_services("default", DEFAULT_SERVICES, *base)
check_services("development override", DEFAULT_SERVICES, *development)
check_services(
    "default with rust profile",
    DEFAULT_SERVICES | {"rust-svc"},
    "--profile",
    "rust",
    *base,
)
check_services(
    "development override with rust profile",
    DEFAULT_SERVICES | {"rust-svc"},
    "--profile",
    "rust",
    *development,
)
check_services("production", PRODUCTION_SERVICES, *production)
check_services(
    "production with rust profile",
    PRODUCTION_SERVICES | {"rust-svc"},
    "--profile",
    "rust",
    *production,
)

check_rust_configuration("development", rust_config(*base), expect_host_port=True)
check_rust_configuration(
    "production", rust_config(*production), expect_host_port=False
)
print("Compose Rust profile regression checks passed.")
