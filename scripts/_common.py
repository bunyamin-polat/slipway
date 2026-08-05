"""Shared plumbing for the deploy and destroy scripts.

Not a script itself. Underscored so it reads as private and never turns up in a
`scripts/` listing as something you are supposed to run.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
import sys
import time
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = REPO_ROOT / "terraform"
ENVS_DIR = TERRAFORM_DIR / "envs"
APP_STACK = TERRAFORM_DIR / "stacks" / "20_app"
BUILD_CONTEXT = REPO_ROOT / "template"
DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.fastapi"
STATIC_DIR = REPO_ROOT / "template" / "app" / "static"

ENVIRONMENTS = ("dev", "test", "prod")
LAMBDA_PLATFORM = "linux/amd64"


class DeployError(Exception):
    """Something went wrong that the user needs to read, not a stack trace."""


def step(message: str) -> None:
    print(f"\n\033[1m▸ {message}\033[0m", flush=True)


def detail(message: str) -> None:
    print(f"  {message}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    """Run a command, echoing it first. Raises DeployError with context on failure."""
    detail(f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            check=True,
            capture_output=capture,
        )
    except FileNotFoundError as exc:
        raise DeployError(f"{cmd[0]} is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise DeployError(
            f"`{' '.join(cmd)}` failed with exit code {exc.returncode}"
            + (f"\n{output}" if output else "")
        ) from exc
    return (result.stdout or "").strip() if capture else ""


def timed(label: str) -> Timer:
    return Timer(label)


class Timer:
    """Print how long a phase took. Deploy duration is a number worth knowing."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.started = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> Timer:
        self.started = time.monotonic()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed = time.monotonic() - self.started
        detail(f"{self.label} took {self.elapsed:.1f}s")


def require_environment(name: str) -> str:
    if name not in ENVIRONMENTS:
        raise DeployError(
            f"Unknown environment {name!r}. Expected one of: {', '.join(ENVIRONMENTS)}"
        )
    return name


def tfvars_file(environment: str) -> Path:
    path = ENVS_DIR / f"{environment}.tfvars"
    if not path.exists():
        raise DeployError(
            f"{path} does not exist.\n"
            f"  cp {path.with_suffix('.tfvars.example')} {path}\n"
            "  then edit it. *.tfvars is gitignored on purpose."
        )
    return path


def backend_config(stack: Path) -> Path:
    path = stack / "backend.hcl"
    if not path.exists():
        raise DeployError(
            f"{path} does not exist.\n"
            f"  cp {stack / 'backend.hcl.example'} {path}\n"
            "  then set `bucket` to the output of:\n"
            "  terraform -chdir=terraform/stacks/00_bootstrap output -raw state_bucket_name"
        )
    return path


def aws_identity() -> tuple[str, str]:
    """Return (account_id, region), failing with something readable if credentials are stale."""
    session = boto3.session.Session()
    region = session.region_name
    if not region:
        raise DeployError("No AWS region configured. Set one in your profile or export AWS_REGION.")
    try:
        account_id = session.client("sts").get_caller_identity()["Account"]
    except Exception as exc:  # noqa: BLE001 — botocore raises a family of unrelated types
        raise DeployError(
            f"Could not reach AWS: {exc}\n"
            "  If the SSO session expired: aws sso login --profile slipway"
        ) from exc
    return account_id, region


def registry_url(account_id: str, region: str) -> str:
    return f"{account_id}.dkr.ecr.{region}.amazonaws.com"


def ecr_login(region: str) -> None:
    """Log Docker into ECR using a short-lived token from the current AWS session."""
    client = boto3.client("ecr", region_name=region)
    auth = client.get_authorization_token()["authorizationData"][0]
    username, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    endpoint = auth["proxyEndpoint"]

    detail(f"$ docker login {endpoint}")
    result = subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", endpoint],
        input=password,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeployError(f"docker login failed:\n{result.stderr.strip()}")


def git_tag() -> str:
    """Short commit SHA, marked dirty when the tree has uncommitted changes.

    Tagging by commit is what makes a rollback a re-apply instead of an archaeology
    project: the running image always points back at a specific commit.
    """
    sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture=True)
    dirty = run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture=True)
    return f"{sha}-dirty" if dirty else sha


def terraform(args: list[str], stack: Path) -> str:
    return run(["terraform", *args], cwd=stack, capture=False)


def terraform_output(name: str, stack: Path) -> str:
    return run(["terraform", "output", "-raw", name], cwd=stack, capture=True)


def terraform_outputs(stack: Path) -> dict[str, object]:
    """All outputs at once. Cheaper than one `terraform output` call per value."""
    raw = run(["terraform", "output", "-json"], cwd=stack, capture=True)
    return {key: value.get("value") for key, value in json.loads(raw).items()}


def sync_static(directory: Path, bucket: str) -> int:
    """Upload the static files, setting content types and cache headers as we go.

    S3 has no notion of a default content type: an object uploaded without one is served
    as application/octet-stream and the browser downloads the page instead of rendering it.
    """
    client = boto3.client("s3")
    uploaded = 0

    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue

        key = str(path.relative_to(directory))
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        # HTML is revalidated every time so a deploy is visible immediately; the
        # invalidation is a belt-and-braces measure on top of it. Fingerprinted assets
        # could be cached forever, but this app has none.
        cache_control = "no-cache" if path.suffix in {".html", ".json"} else "public, max-age=3600"

        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type, "CacheControl": cache_control},
        )
        detail(f"uploaded {key} ({content_type})")
        uploaded += 1

    return uploaded


def invalidate(distribution_id: str, paths: list[str] | None = None) -> str:
    """File a CloudFront invalidation and return its ID, without waiting for it.

    Waiting would add minutes to every deploy for no benefit — the invalidation completes
    on its own, and the first request afterwards gets fresh content either way.
    """
    client = boto3.client("cloudfront")
    response = client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": paths or ["/*"]},
            "CallerReference": str(time.time()),
        },
    )
    return response["Invalidation"]["Id"]


def select_workspace(environment: str, stack: Path) -> None:
    """Select the workspace, creating it the first time."""
    existing = run(["terraform", "workspace", "list"], cwd=stack, capture=True)
    names = {line.strip().lstrip("* ").strip() for line in existing.splitlines()}
    if environment in names:
        terraform(["workspace", "select", environment], stack)
    else:
        detail(f"workspace {environment} does not exist yet, creating it")
        terraform(["workspace", "new", environment], stack)


def fail(exc: DeployError) -> int:
    print(f"\n\033[31mFailed:\033[0m {exc}", file=sys.stderr)
    return 1
