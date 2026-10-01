"""Exercise deployment proxy settings through Uvicorn, login, and persisted audits."""

import asyncio
import ipaddress
import json
import re
import shlex
import shutil
import socket
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from httpx2 import ASGITransport, AsyncClient, HTTPError
from uvicorn import Config, Server

from src.domain.value_objects import EventType
from src.infrastructure.repositories import AuditEventRepositoryImpl

ROOT = Path(__file__).resolve().parents[3]
PROXY_IP = "172.30.0.2"
CLIENT_IP = "203.0.113.4"
CONFIGURATIONS = ["default", "dev", "prod"]


def compose_configuration(configuration):
    filename = "docker-compose.prod.yml" if configuration == "prod" else "docker-compose.yml"
    document = yaml.safe_load((ROOT / filename).read_text())
    if configuration == "dev":
        override = yaml.safe_load((ROOT / "docker-compose.override.yml").read_text())
        api = document["services"]["api"]
        api["command"] = override["services"]["api"]["command"]
        environment = override["services"]["api"].get("environment", {})
        if isinstance(environment, list):
            environment = dict(item.split("=", 1) for item in environment)
        api["environment"] = {**api.get("environment", {}), **environment}
    return document


def default_value(value):
    return re.sub(r"\$\{[^:}]+:-([^}]+)\}", r"\1", value)


def server_config(app, configuration, monkeypatch, **kwargs):
    api = compose_configuration(configuration)["services"]["api"]
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    environment = api.get("environment", {})
    if "FORWARDED_ALLOW_IPS" in environment:
        monkeypatch.setenv("FORWARDED_ALLOW_IPS", default_value(environment["FORWARDED_ALLOW_IPS"]))
    else:
        dockerfile = (ROOT / "apps/api/Dockerfile").read_text()
        match = re.search(r'FORWARDED_ALLOW_IPS="([^"]*)"', dockerfile)
        if match:
            monkeypatch.setenv("FORWARDED_ALLOW_IPS", match[1])
    command = shlex.split(api.get("command", ""))
    return Config(app, proxy_headers="--no-proxy-headers" not in command, log_config=None, **kwargs)


async def login(client):
    account = {"email": "proxy@example.com", "password": "CorrectHorse1!"}
    response = await client.post("/api/v1/auth/register", json=account)
    assert response.status_code == 201, response.text
    return account


async def assert_login_ip(db_sessions, expected_ip):
    async with db_sessions() as session:
        events, count = await AuditEventRepositoryImpl(session).list(
            event_type=EventType.USER_LOGGED_IN
        )
        assert count == 1
        assert events[0].details == {"ip": expected_ip}


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        (PROXY_IP, CLIENT_IP, CLIENT_IP),
        (PROXY_IP, f"198.51.100.99, {CLIENT_IP}", CLIENT_IP),
        (PROXY_IP, "2001:db8::4", "2001:db8::4"),
        (CLIENT_IP, "198.51.100.99", CLIENT_IP),
        ("172.30.0.1", "198.51.100.99", "172.30.0.1"),
        ("172.30.0.3", "198.51.100.99", "172.30.0.3"),
        ("127.0.0.1", "198.51.100.99", "127.0.0.1"),
        ("::1", "198.51.100.99", "::1"),
    ],
)
async def test_compose_proxy_login_audits_client_ip(
    app, db_sessions, monkeypatch, configuration, peer, forwarded, expected
):
    config = server_config(app, configuration, monkeypatch)
    config.load()
    transport = ASGITransport(app=config.loaded_app, client=(peer, 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account = await login(client)
        response = await client.post(
            "/api/v1/auth/login",
            json=account,
            headers={"X-Forwarded-For": forwarded, "X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 200, response.text
    await assert_login_ip(db_sessions, expected)


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_compose_trust_matches_only_nginx_on_shared_gateway(configuration):
    document = compose_configuration(configuration)
    services = document["services"]
    trusted_ip = default_value(services["api"]["environment"]["FORWARDED_ALLOW_IPS"])
    proxy_networks = services["nginx"]["networks"]
    assert set(proxy_networks) == {"gateway"}
    assert trusted_ip == default_value(proxy_networks["gateway"]["ipv4_address"])
    subnet = ipaddress.ip_network(
        default_value(document["networks"]["gateway"]["ipam"]["config"][0]["subnet"])
    )
    assert ipaddress.ip_address(trusted_ip) in subnet
    dynamic = ipaddress.ip_network(
        default_value(document["networks"]["gateway"]["ipam"]["config"][0]["ip_range"])
    )
    assert dynamic.subnet_of(subnet)
    assert ipaddress.ip_address(trusted_ip) not in dynamic
    assert set(services["api"]["networks"]) == {"default", "gateway"}
    assert set(services["web"]["networks"]) == {"default", "gateway"}
    if configuration == "prod":
        assert "ports" not in services["api"]
    else:
        assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]


def test_standalone_and_local_startup_do_not_trust_forwarded_headers():
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text()
    assert 'FORWARDED_ALLOW_IPS=""' in dockerfile
    command = json.loads(
        next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD "))
    )
    assert "--proxy-headers" in command
    for filename in ("Makefile", "apps/api/moon.yml", "apps/api/README.md", "apps/api/main.py"):
        commands = [
            line for line in (ROOT / filename).read_text().splitlines() if "uvicorn " in line
        ]
        assert commands
        assert all("--no-proxy-headers" in command for command in commands)


def test_nginx_replaces_untrusted_forwarding_headers():
    headers = (ROOT / "nginx/snippets/proxy-headers.conf").read_text()
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in headers
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in headers
    assert "$proxy_add_x_forwarded_for" not in headers
    routes = (ROOT / "nginx/conf.d/app.conf").read_text()
    assert routes.count("include /etc/nginx/snippets/proxy-headers.conf;") == 3


@pytest.mark.parametrize("startup", ["docker", "local"])
@pytest.mark.parametrize("peer", ["127.0.0.1", "::1"])
async def test_direct_local_login_ignores_spoofed_headers(
    app, db_sessions, monkeypatch, startup, peer
):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "" if startup == "docker" else "*")
    config = Config(app, proxy_headers=startup == "docker", log_config=None)
    config.load()
    transport = ASGITransport(app=config.loaded_app, client=(peer, 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account = await login(client)
        response = await client.post(
            "/api/v1/auth/login",
            json=account,
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        assert response.status_code == 200, response.text
    await assert_login_ip(db_sessions, peer)


async def docker(*arguments):
    process = await asyncio.create_subprocess_exec(
        "docker", *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    assert process.returncode == 0, stderr.decode()
    return stdout.decode()


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker is required for real nginx smoke"
)
@pytest.mark.parametrize("configuration", CONFIGURATIONS)
async def test_real_nginx_discards_spoofed_header_before_login_audit(
    app, db_sessions, monkeypatch, tmp_path, configuration
):
    """Run nginx's shipped header snippet over TCP, including duplicate spoofed headers."""
    network = f"audit-proxy-{uuid4().hex}"
    container = f"{network}-nginx"
    document = compose_configuration(configuration)
    ipam = document["networks"]["gateway"]["ipam"]["config"][0]
    subnet = default_value(ipam["subnet"])
    dynamic = default_value(ipam["ip_range"])
    gateway = str(ipaddress.ip_network(subnet).network_address + 1)
    peer = str(ipaddress.ip_network(subnet).network_address + 3)
    proxy = default_value(document["services"]["nginx"]["networks"]["gateway"]["ipv4_address"])
    listener = socket.socket()
    listener.bind(("0.0.0.0", 0))
    listener.listen()
    port = listener.getsockname()[1]
    config = server_config(app, configuration, monkeypatch, lifespan="off", access_log=False)
    server = Server(config)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    nginx_config = tmp_path / "nginx.conf"
    nginx_config.write_text(
        "events {}\nhttp {\n"
        "map $http_upgrade $connection_upgrade { default upgrade; '' close; }\n"
        "server { listen 8080; location / {\n"
        f"proxy_pass http://{gateway}:{port};\n"
        "include /etc/nginx/snippets/proxy-headers.conf;\n"
        "} }\n}\n"
    )
    network_created = False
    container_created = False
    try:
        await docker("network", "create", "--subnet", subnet, "--ip-range", dynamic, network)
        network_created = True
        await docker(
            "run",
            "-d",
            "--name",
            container,
            "--network",
            network,
            "--ip",
            proxy,
            "-v",
            f"{nginx_config}:/etc/nginx/nginx.conf:ro",
            "-v",
            f"{ROOT / 'nginx/snippets'}:/etc/nginx/snippets:ro",
            "nginx:1.27-alpine",
        )
        container_created = True
        async with AsyncClient(base_url=f"http://{proxy}:8080", trust_env=False) as client:
            for attempt in range(50):
                try:
                    response = await client.get("/api/v1/health", timeout=1)
                    if response.status_code == 200:
                        break
                except HTTPError:
                    if task.done():
                        await task
                        raise
                await asyncio.sleep(0.1)
            else:
                pytest.fail("nginx/Uvicorn did not become ready")
            account = await login(client)
        # A separate container's real TCP source address must win over both forged headers.
        await docker(
            "run",
            "--rm",
            "--network",
            network,
            "--ip",
            peer,
            "curlimages/curl:8.12.1",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--max-time",
            "10",
            "-H",
            "Content-Type: application/json",
            "-H",
            "X-Forwarded-For: 198.51.100.99",
            "-H",
            f"X-Forwarded-For: {proxy}, 127.0.0.1",
            "-H",
            "X-Forwarded-Proto: https",
            "--data",
            json.dumps(account),
            f"http://{proxy}:8080/api/v1/auth/login",
        )
        await assert_login_ip(db_sessions, peer)
    finally:
        server.should_exit = True
        try:
            if container_created:
                await docker("rm", "-f", container)
            if network_created:
                await docker("network", "rm", network)
        finally:
            await asyncio.wait_for(task, timeout=5)
            listener.close()
