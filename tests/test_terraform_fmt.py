"""Formatting and validity checks across every module and stack.

Cheap, fast, and much less annoying as a test than as a review comment.

Validation runs against a **copy** of `terraform/` in a temporary directory. Running
`terraform init` inside the real stacks would reconfigure their backends and demand AWS
credentials for a check that needs neither — a test that breaks your working directory is
worse than no test.

Skipped rather than failed when Terraform is not installed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = REPO_ROOT / "terraform"

terraform_required = pytest.mark.skipif(
    shutil.which("terraform") is None,
    reason="terraform is not installed",
)


def terraform_dirs() -> list[Path]:
    """Every directory holding .tf files, relative to terraform/.

    Discovered rather than listed, so a new module is covered without editing this file.
    """
    return sorted({path.parent.relative_to(TERRAFORM_DIR) for path in TERRAFORM_DIR.rglob("*.tf")})


@pytest.fixture(scope="session")
def terraform_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway copy of terraform/, without state, backends or real variable values."""
    destination = tmp_path_factory.mktemp("tf") / "terraform"
    shutil.copytree(
        TERRAFORM_DIR,
        destination,
        ignore=shutil.ignore_patterns(
            ".terraform",
            "*.tfstate",
            "*.tfstate.*",
            "backend.hcl",
            "*.tfvars",
        ),
    )
    return destination


@pytest.fixture(scope="session")
def plugin_cache(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Share downloaded providers across directories instead of fetching them each time."""
    cache = tmp_path_factory.mktemp("tf-plugins")
    return {"TF_PLUGIN_CACHE_DIR": str(cache)}


@terraform_required
def test_everything_is_formatted() -> None:
    result = subprocess.run(
        ["terraform", "fmt", "-check", "-recursive", str(TERRAFORM_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "These files need `terraform fmt -recursive`:\n" + result.stdout.strip()
    )


@terraform_required
@pytest.mark.parametrize("relative", terraform_dirs(), ids=lambda p: p.name)
def test_configuration_is_valid(
    relative: Path,
    terraform_tree: Path,
    plugin_cache: dict[str, str],
) -> None:
    directory = terraform_tree / relative

    init = subprocess.run(
        ["terraform", "init", "-backend=false", "-input=false"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        env={**plugin_cache, "PATH": subprocess.os.environ["PATH"], "HOME": str(Path.home())},
    )
    assert init.returncode == 0, f"terraform init failed in {relative}:\n{init.stderr}"

    validate = subprocess.run(
        ["terraform", "validate", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, f"{relative} is invalid:\n{validate.stdout}"
