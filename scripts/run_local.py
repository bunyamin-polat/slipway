#!/usr/bin/env python3
"""Build the example app's image and run it locally, under the same env contract.

The point is that this is not a different way of running the app. It is the same
image, the same port, the same environment variables that Lambda will use — so a
thing that works here has a real chance of working there.

    uv run python scripts/run_local.py
    uv run python scripts/run_local.py --native   # skip amd64 emulation, faster on ARM

Ctrl-C stops and removes the container.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_CONTEXT = REPO_ROOT / "template"
DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.fastapi"

IMAGE = "slipway-app:local"
CONTAINER = "slipway-app-local"
PORT = 8080

# Lambda runs x86_64 images. An image built on Apple Silicon without this flag fails
# there with an opaque "Runtime.InvalidEntrypoint", so it is the default here too:
# local and deployed should differ as little as possible.
LAMBDA_PLATFORM = "linux/amd64"


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing it first so the output reads like a transcript."""
    print(f"\n$ {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd, text=True, check=True, **kwargs)  # type: ignore[call-overload]


def docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True


def remove_existing_container() -> None:
    """Remove a container left behind by a previous run, if any."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER}$"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        print(f"Removing previous container {CONTAINER}")
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)


def build(native: bool) -> None:
    cmd = ["docker", "build"]
    if not native:
        cmd += ["--platform", LAMBDA_PLATFORM]
    # Docker 28 attaches provenance and SBOM attestations by default, which turns the
    # image into a manifest index carrying an `unknown/unknown` entry. Lambda cannot
    # resolve that and rejects the image with "media type ... is not supported" —
    # a message that mentions nothing about attestations. Same flags as the deploy
    # path, so what runs here is what gets pushed.
    cmd += ["--provenance=false", "--sbom=false"]
    cmd += ["-f", str(DOCKERFILE), "-t", IMAGE, str(BUILD_CONTEXT)]
    run(cmd)


def start(native: bool) -> None:
    cmd = ["docker", "run", "-d", "--name", CONTAINER, "-p", f"{PORT}:{PORT}"]
    if not native:
        cmd += ["--platform", LAMBDA_PLATFORM]
    cmd += [IMAGE]
    run(cmd)


def wait_for_health(timeout: float = 60.0) -> bool:
    """Poll /healthz until the server answers or we give up."""
    url = f"http://localhost:{PORT}/healthz"
    deadline = time.monotonic() + timeout
    print(f"Waiting for {url}", end="", flush=True)

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    print(" ok")
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        print(".", end="", flush=True)
        time.sleep(1)

    print(" gave up")
    return False


def stop() -> None:
    print(f"\nStopping {CONTAINER}")
    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native",
        action="store_true",
        help="Build for this machine's architecture instead of linux/amd64. Faster on "
        "Apple Silicon, but no longer the image Lambda would run.",
    )
    args = parser.parse_args()

    if not docker_available():
        print("Docker is not running. Start Docker Desktop and try again.", file=sys.stderr)
        return 1

    if args.native and platform.machine() in {"arm64", "aarch64"}:
        print("Building natively for arm64 — this is NOT the image Lambda will run.")

    remove_existing_container()

    try:
        build(args.native)
        start(args.native)
    except subprocess.CalledProcessError as exc:
        print(f"\nDocker command failed with exit code {exc.returncode}", file=sys.stderr)
        stop()
        return exc.returncode

    if not wait_for_health():
        print("\nContainer never became healthy. Last 40 lines of its log:", file=sys.stderr)
        subprocess.run(["docker", "logs", "--tail", "40", CONTAINER], check=False)
        stop()
        return 1

    print(f"\n  Running on http://localhost:{PORT}")
    print("  Open it and press Stream — the words should arrive one at a time.")
    print("  Ctrl-C to stop.\n")

    try:
        subprocess.run(["docker", "logs", "-f", CONTAINER], check=False)
    except KeyboardInterrupt:
        pass
    finally:
        stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
