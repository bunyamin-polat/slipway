"""`slipway.yaml` is the one file an adopter fills in, so it is worth testing properly.

The interesting cases are the ones where a mistake would otherwise reach AWS: an unknown
environment, a compute target that does not exist, a Dockerfile path that does not.
"""

from pathlib import Path

import pytest
import yaml
from _common import REPO_ROOT, DeployError, load_config

REAL_CONFIG = REPO_ROOT / "slipway.yaml"


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "slipway.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


BASE = {
    "name": "demo",
    "region": "eu-west-1",
    "image": {
        "repository": "demo-app",
        "dockerfile": "docker/Dockerfile.fastapi",
        "context": "template",
        "static_dir": "template/app/static",
    },
    "compute": {"target": "lambda", "memory": 512, "timeout": 15},
    "environments": {
        "dev": {"cdn": False, "observability": True, "log_retention_days": 3},
        "prod": {"cdn": True, "observability": True, "log_retention_days": 30},
    },
}


def test_the_repos_own_config_loads() -> None:
    """This repository is its own first adopter; if this fails, so does every deploy."""
    for environment in ("dev", "test", "prod"):
        config = load_config(environment, REAL_CONFIG)
        assert config.name == "slipway"
        assert config.compute_target in {"lambda", "apprunner"}
        assert config.dockerfile.exists()


def test_environment_values_win_over_defaults(tmp_path: Path) -> None:
    config = load_config("prod", write(tmp_path, BASE))

    assert config.resource_prefix == "demo-prod"
    assert config.cdn is True
    assert config.log_retention_days == 30
    assert config.memory == 512  # inherited, not overridden


def test_an_environment_can_override_the_compute_target(tmp_path: Path) -> None:
    """The one override that changes the shape of the environment rather than a number."""
    data = {**BASE, "environments": {**BASE["environments"]}}
    data["environments"]["bench"] = {
        "compute": {"target": "apprunner", "apprunner": {"cpu": "1 vCPU"}},
        "cdn": False,
    }

    config = load_config("bench", write(tmp_path, data))

    assert config.compute_target == "apprunner"
    assert config.apprunner_cpu == "1 vCPU"
    assert config.apprunner_memory == "0.5 GB"  # untouched default


def test_unknown_environment_names_the_ones_that_exist(tmp_path: Path) -> None:
    with pytest.raises(DeployError) as exc:
        load_config("staging", write(tmp_path, BASE))

    assert "staging" in str(exc.value)
    assert "dev" in str(exc.value) and "prod" in str(exc.value)


def test_an_impossible_compute_target_is_refused(tmp_path: Path) -> None:
    data = {**BASE, "compute": {"target": "kubernetes"}}

    with pytest.raises(DeployError, match="lambda or apprunner"):
        load_config("dev", write(tmp_path, data))


def test_a_missing_dockerfile_is_caught_before_aws_is_touched(tmp_path: Path) -> None:
    data = {**BASE, "image": {**BASE["image"], "dockerfile": "docker/Dockerfile.nope"}}

    with pytest.raises(DeployError, match="Dockerfile not found"):
        load_config("dev", write(tmp_path, data))


def test_terraform_vars_cover_every_variable_the_stack_declares() -> None:
    """The failure this prevents: adding a variable and forgetting to pass it.

    Terraform would then prompt for it, and in CI a prompt is a hang, not an error.
    """
    declared = (REPO_ROOT / "terraform/stacks/20_app/variables.tf").read_text()
    names = {line.split('"')[1] for line in declared.splitlines() if line.startswith("variable ")}

    passed = {v.removeprefix("-var=").split("=")[0] for v in load_config("dev").terraform_vars("t")}

    assert names == passed, f"missing: {names - passed}, unexpected: {passed - names}"
