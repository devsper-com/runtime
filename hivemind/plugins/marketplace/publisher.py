import subprocess, hashlib, os, sys
from pathlib import Path
import httpx


class PublishError(Exception):
    pass


class PluginPublisher:
    REGISTRY_URL = os.environ.get(
        "HIVEMIND_REGISTRY_URL", "https://registry.hivemind.rithul.dev"
    )

    def publish(self, package_dir: str = ".") -> None:
        path = Path(package_dir).resolve()
        self._validate_plugin(path)
        dist_files = self._build(path)
        token = self._get_token()
        for f in dist_files:
            self._upload(f, token)

    def _validate_plugin(self, path: Path) -> None:
        pyproject = path / "pyproject.toml"
        if not pyproject.exists():
            raise PublishError("No pyproject.toml found")
        content = pyproject.read_text()
        if "hivemind.plugins" not in content:
            raise PublishError(
                'No [project.entry-points."hivemind.plugins"] section found. '
                "This package is not a valid hivemind plugin."
            )

    def _build(self, path: Path) -> list[Path]:
        print("Building package...")
        result = subprocess.run(
            ["python", "-m", "build", "--outdir", str(path / "dist")],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PublishError(f"Build failed:\n{result.stderr}")
        dist = path / "dist"
        files = list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz"))
        if not files:
            raise PublishError("Build produced no dist files")
        return files

    def _get_token(self) -> str:
        # Check env first (for CI)
        token = os.environ.get("HIVEMIND_API_KEY")
        if token:
            return token
        # Check credential store (from v1.3 secure store)
        try:
            from hivemind.credentials.store import get_credential

            token = get_credential("hivemind_registry", "api_key")
            if token:
                return token
        except ImportError:
            pass
        raise PublishError(
            "No API key found. Set HIVEMIND_API_KEY env var or run:\n"
            "  hivemind plugins login"
        )

    def _upload(self, file: Path, token: str) -> None:
        sha256 = hashlib.sha256(file.read_bytes()).hexdigest()
        print(f"Uploading {file.name}...")
        try:
            with httpx.Client() as client:
                r = client.post(
                    f"{self.REGISTRY_URL}/api/v1/packages/upload",
                    headers={"X-API-Key": token},
                    files={
                        "content": (
                            file.name,
                            file.open("rb"),
                            "application/octet-stream",
                        )
                    },
                    data={
                        "sha256_digest": sha256,
                        "filetype": "bdist_wheel" if file.suffix == ".whl" else "sdist",
                    },
                    timeout=120.0,
                )
            if r.status_code == 201:  # Changed to 201 Created as per handler
                print(f"Uploaded successfully: {file.name}")
            elif r.status_code == 202:
                data = r.json()
                print(f"Uploaded. Verification pending: {data.get('file_id')}")
            elif r.status_code == 401:
                raise PublishError("Invalid API key. Run: hivemind plugins login")
            elif r.status_code == 409:
                data = r.json()
                msg = data.get("error", "Version already exists")
                raise PublishError(f"Version already exists: {msg}")
            else:
                raise PublishError(f"Upload failed ({r.status_code}): {r.text}")
        except httpx.RequestError as e:
            raise PublishError(f"Connection error: {e}")


def cmd_login():
    registry_url = os.environ.get(
        "HIVEMIND_REGISTRY_URL", "https://registry.hivemind.rithul.dev"
    )
    print(f"Get your API key from: {registry_url}/dashboard/api-keys")
    import getpass

    key = getpass.getpass("API key (hm_...): ").strip()
    if not key.startswith("hm_"):
        print("Warning: key doesn't start with hm_ — double-check it")

    try:
        from hivemind.credentials.store import set_credential

        set_credential("hivemind_registry", "api_key", key)
        print("API key stored securely in system keychain.")
    except ImportError:
        print("Error: Could not access credential store.")
