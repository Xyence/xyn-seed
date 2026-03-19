import os
import unittest
import uuid
import asyncio

from fastapi import HTTPException
from starlette.requests import Request

from core.access_control import (
    CAP_CAMPAIGNS_MANAGE,
    CAP_JURISDICTIONS_MANAGE,
    ROLE_APPLICATION_ADMIN,
    ROLE_CAMPAIGN_OPERATOR,
    ROLE_READ_ONLY_ANALYST,
    AccessDeniedError,
    AccessPrincipal,
    assert_access,
    principal_from_request,
    resolve_effective_capabilities,
)
from core.api.access import access_me, list_access_roles


def _request_with_headers(headers: dict[str, str] | None = None) -> Request:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": encoded_headers,
        }
    )


class AccessControlTests(unittest.TestCase):
    def setUp(self):
        self._auth_mode = os.environ.get("XYN_AUTH_MODE")

    def tearDown(self):
        if self._auth_mode is None:
            os.environ.pop("XYN_AUTH_MODE", None)
        else:
            os.environ["XYN_AUTH_MODE"] = self._auth_mode

    def test_role_mapping_campaign_operator_has_campaign_capability(self):
        capabilities = set(resolve_effective_capabilities(roles=[ROLE_CAMPAIGN_OPERATOR]))
        self.assertIn(CAP_CAMPAIGNS_MANAGE, capabilities)
        self.assertNotIn(CAP_JURISDICTIONS_MANAGE, capabilities)

    def test_read_only_analyst_is_denied_mutation_capability(self):
        principal = AccessPrincipal(
            subject_id="analyst",
            roles=(ROLE_READ_ONLY_ANALYST,),
            capabilities=resolve_effective_capabilities(roles=[ROLE_READ_ONLY_ANALYST]),
        )
        with self.assertRaises(AccessDeniedError):
            assert_access(principal, required_capabilities=[CAP_CAMPAIGNS_MANAGE])

    def test_scope_enforcement_rejects_workspace_mismatch(self):
        principal = AccessPrincipal(
            subject_id="operator",
            roles=(ROLE_CAMPAIGN_OPERATOR,),
            capabilities=resolve_effective_capabilities(roles=[ROLE_CAMPAIGN_OPERATOR]),
            workspace_scope_id=uuid.uuid4(),
        )
        with self.assertRaises(AccessDeniedError):
            assert_access(
                principal,
                required_capabilities=[CAP_CAMPAIGNS_MANAGE],
                workspace_id=uuid.uuid4(),
            )

    def test_dev_mode_defaults_to_application_admin_when_roles_missing(self):
        os.environ["XYN_AUTH_MODE"] = "dev"
        principal = principal_from_request(_request_with_headers())
        self.assertIn(ROLE_APPLICATION_ADMIN, principal.roles)
        self.assertEqual(principal.subject_id, "dev-user")


class AccessApiTests(unittest.TestCase):
    def setUp(self):
        self._auth_mode = os.environ.get("XYN_AUTH_MODE")

    def tearDown(self):
        if self._auth_mode is None:
            os.environ.pop("XYN_AUTH_MODE", None)
        else:
            os.environ["XYN_AUTH_MODE"] = self._auth_mode

    def test_access_roles_requires_capability(self):
        os.environ["XYN_AUTH_MODE"] = "token"
        denied_principal = principal_from_request(_request_with_headers())
        with self.assertRaises(HTTPException):
            asyncio.run(list_access_roles(principal=denied_principal))

        allowed_principal = principal_from_request(
            _request_with_headers({"X-Roles": ROLE_CAMPAIGN_OPERATOR, "X-User-Id": "operator"})
        )
        result = asyncio.run(list_access_roles(principal=allowed_principal))
        self.assertIn(ROLE_CAMPAIGN_OPERATOR, result["roles"])

    def test_access_me_reflects_scope_headers(self):
        req = _request_with_headers(
            {
                "X-Roles": ROLE_READ_ONLY_ANALYST,
                "X-User-Id": "analyst-1",
                "X-Application-Slug": "deal-finder",
                "X-Access-Workspace-Id": str(uuid.uuid4()),
            }
        )
        principal = principal_from_request(req)
        result = asyncio.run(access_me(request=req, principal=principal))
        self.assertEqual(result["subject_id"], "analyst-1")
        self.assertEqual(result["application_scope"], "deal-finder")
        self.assertIn(ROLE_READ_ONLY_ANALYST, result["roles"])


if __name__ == "__main__":
    unittest.main()
