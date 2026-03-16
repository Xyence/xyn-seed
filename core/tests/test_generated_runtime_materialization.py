from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.app_jobs import _materialize_net_inventory_compose, _prefer_local_platform_images_for_smoke
from core.provisioning_local import ProvisionLocalRequest, _ensure_remote_workspace, _resolve_images_for_provision


class GeneratedRuntimeMaterializationTests(unittest.TestCase):
    def test_compose_injects_manifest_entity_contracts(self):
        app_spec = {
            "app_slug": "net-inventory",
            "title": "Network Inventory App",
            "workspace_id": "workspace-1",
            "entities": ["devices", "locations"],
            "reports": ["devices_by_status"],
            "services": [
                {"name": "net-inventory-api", "image": "net-inventory-api:local", "ports": [{"host": 0, "container": 8080, "protocol": "tcp"}]},
                {"name": "net-inventory-db", "image": "postgres:16-alpine"},
            ],
            "requires_primitives": ["location"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_path = _materialize_net_inventory_compose(
                app_spec=app_spec,
                deployment_dir=Path(tmpdir),
                compose_project="xyn-app-net-inventory",
            )
            text = compose_path.read_text(encoding="utf-8")

        self.assertIn("GENERATED_ENTITY_CONTRACTS_JSON", text)
        self.assertIn("GENERATED_ENTITY_CONTRACTS_ALLOW_DEFAULTS", text)
        self.assertIn('"key":"devices"', text)
        self.assertIn('"key":"locations"', text)

    def test_workspace_seed_creates_missing_workspace(self):
        class _FakeResponse:
            def __init__(self, status: int, body: str = "", headers: dict[str, str] | None = None):
                self.status = status
                self._body = body.encode("utf-8")
                self.headers = headers or {}

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        opener = mock.Mock()
        opener.open.side_effect = [
            _FakeResponse(302, headers={"Set-Cookie": "sessionid=abc123; Path=/"}),
            _FakeResponse(200, body='{"workspaces":[{"id":"default-1","slug":"default"}]}'),
            _FakeResponse(201, body='{"workspace":{"id":"w-1","slug":"epicb-lab"}}'),
        ]
        with mock.patch("core.provisioning_local.urllib.request.build_opener", return_value=opener):
            result = _ensure_remote_workspace(
                api_url="http://api.example.test",
                workspace_slug="epicb-lab",
                workspace_title="Epicb Lab",
            )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["workspace_slug"], "epicb-lab")
        self.assertEqual(opener.open.call_count, 3)

    @mock.patch("core.provisioning_local.SessionLocal")
    @mock.patch("core.provisioning_local.resolve_registry_images")
    def test_provision_prefers_artifact_registry_by_default(self, resolve_registry_images, session_local):
        session_local.return_value = mock.Mock()
        resolve_registry_images.return_value = {
            "registry": {"endpoint": "public.ecr.aws/i0h0h0n4/xyn/artifacts"},
            "images": {
                "ui_image": "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-ui:dev",
                "api_image": "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-api:dev",
                "channel": "dev",
            },
            "registry_slug": "default-registry",
            "registry_source": "default-registry",
            "operations": ["Using ArtifactRegistry: default-registry"],
        }
        with mock.patch("core.provisioning_local._docker_image_exists", return_value=True):
            result = _resolve_images_for_provision(ProvisionLocalRequest(name="smoke"))

        self.assertEqual(result["mode"], "artifact_registry")
        self.assertEqual(result["api_image"], "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-api:dev")
        self.assertEqual(result["ui_image"], "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-ui:dev")
        resolve_registry_images.assert_called_once()

    @mock.patch("core.provisioning_local._docker_image_exists", return_value=True)
    @mock.patch("core.provisioning_local._running_container_image_ref")
    def test_provision_prefers_running_local_platform_images(self, running_container_image_ref, _docker_image_exists):
        running_container_image_ref.side_effect = [
            "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-api:dev",
            "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-ui:dev",
        ]

        result = _resolve_images_for_provision(ProvisionLocalRequest(name="smoke", prefer_local_images=True))

        self.assertEqual(result["mode"], "running_local_images")
        self.assertEqual(result["api_image"], "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-api:dev")
        self.assertEqual(result["ui_image"], "public.ecr.aws/i0h0h0n4/xyn/artifacts/xyn-ui:dev")

    def test_provision_can_opt_into_local_images(self):
        def _run(cmd, *args, **kwargs):
            context = cmd[-1]
            if context in {"/tmp/src/xyn-platform/services/xyn-api", "/tmp/src/xyn-platform/apps/xyn-ui"}:
                return (0, "", "")
            return (1, "", f"missing context: {context}")

        with mock.patch("core.provisioning_local._running_container_image_ref", return_value=""):
            with mock.patch("core.provisioning_local._run", side_effect=_run):
                with mock.patch.dict("os.environ", {"XYN_HOST_SRC_ROOT": "/tmp/src"}, clear=False):
                    result = _resolve_images_for_provision(ProvisionLocalRequest(name="smoke", prefer_local_images=True))

        self.assertEqual(result["mode"], "local_build")
        self.assertEqual(result["api_image"], "xyn-api")
        self.assertEqual(result["ui_image"], "xyn-ui")
        self.assertIn("Built local image xyn-api from /tmp/src/xyn-platform/services/xyn-api", result["operations"])
        self.assertIn("Built local image xyn-ui from /tmp/src/xyn-platform/apps/xyn-ui", result["operations"])

    @mock.patch("core.provisioning_local._docker_image_exists", return_value=True)
    def test_provision_falls_back_to_prebuilt_local_images_when_sources_are_missing(self, _docker_image_exists):
        with mock.patch("core.provisioning_local._running_container_image_ref", return_value=""):
            with mock.patch.dict("os.environ", {"XYN_HOST_SRC_ROOT": "/tmp/src"}, clear=False):
                with mock.patch("core.provisioning_local._run", return_value=(1, "", "missing context")):
                    result = _resolve_images_for_provision(ProvisionLocalRequest(name="smoke", prefer_local_images=True))

        self.assertEqual(result["mode"], "prebuilt_local_images")
        self.assertEqual(result["api_image"], "xyn-api")
        self.assertEqual(result["ui_image"], "xyn-ui")

    def test_app_smoke_prefers_local_platform_images_by_default(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            self.assertTrue(_prefer_local_platform_images_for_smoke())

    def test_app_smoke_can_opt_out_of_local_platform_images(self):
        with mock.patch.dict("os.environ", {"XYN_APP_SMOKE_PREFER_LOCAL_IMAGES": "false"}, clear=False):
            self.assertFalse(_prefer_local_platform_images_for_smoke())


if __name__ == "__main__":
    unittest.main()
