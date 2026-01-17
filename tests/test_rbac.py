"""
Tests for the RBAC module.

Tests cover:
- Model validation and behavior
- Store operations (file-based and memory)
- Enforcer permission checks
- Role hierarchy resolution
- Sensitive resource protection
"""

import pytest
from datetime import datetime, timezone, timedelta

from contextcore.rbac import (
    # Enums
    PrincipalType,
    ResourceType,
    Action,
    PolicyDecision,
    # Models
    Principal,
    Resource,
    Permission,
    Role,
    RoleBinding,
    AccessDecision,
    AccessDeniedError,
    # Built-in
    BUILT_IN_ROLES,
    BUILT_IN_ROLE_IDS,
    # Store
    RBACMemoryStore,
    # Enforcer
    RBACEnforcer,
    PrincipalResolver,
)


class TestModels:
    """Test RBAC models."""

    def test_principal_agent(self):
        """Create an agent principal."""
        principal = Principal(
            id="claude-code",
            principal_type=PrincipalType.AGENT,
            display_name="Claude Code Assistant",
            agent_id="claude-code",
        )
        assert principal.id == "claude-code"
        assert principal.principal_type == PrincipalType.AGENT

    def test_principal_user(self):
        """Create a user principal."""
        principal = Principal(
            id="alice",
            principal_type=PrincipalType.USER,
            display_name="Alice",
            email="alice@example.com",
            groups=["developers"],
        )
        assert principal.principal_type == PrincipalType.USER
        assert principal.email == "alice@example.com"

    def test_resource_matches_wildcard(self):
        """Wildcard resource matches any resource of same type."""
        wildcard = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="*",
        )
        specific = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
        )
        assert wildcard.matches(specific) is True

    def test_resource_matches_exact(self):
        """Exact resource match."""
        res1 = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
        )
        res2 = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
        )
        assert res1.matches(res2) is True

    def test_resource_no_match_different_type(self):
        """Different resource types don't match."""
        res1 = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
        )
        res2 = Resource(
            resource_type=ResourceType.PROJECT,
            resource_id="security",
        )
        assert res1.matches(res2) is False

    def test_permission_allows_action(self):
        """Permission allows configured actions."""
        perm = Permission(
            id="test",
            resource=Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id="*",
            ),
            actions=[Action.READ, Action.QUERY],
        )
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="infrastructure",
        )
        assert perm.allows(Action.READ, resource) is True
        assert perm.allows(Action.WRITE, resource) is False

    def test_permission_expired(self):
        """Expired permissions don't allow access."""
        perm = Permission(
            id="test",
            resource=Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id="*",
            ),
            actions=[Action.READ],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="test",
        )
        assert perm.is_expired() is True
        assert perm.allows(Action.READ, resource) is False

    def test_permission_sensitive_check(self):
        """Non-sensitive permission doesn't allow sensitive resource."""
        perm = Permission(
            id="test",
            resource=Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id="*",
                sensitive=False,
            ),
            actions=[Action.READ],
        )
        sensitive_resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
        )
        assert perm.allows(Action.READ, sensitive_resource) is False


class TestBuiltInRoles:
    """Test built-in roles."""

    def test_built_in_roles_exist(self):
        """Built-in roles are defined."""
        assert len(BUILT_IN_ROLES) >= 4
        assert "reader" in BUILT_IN_ROLE_IDS
        assert "agent-standard" in BUILT_IN_ROLE_IDS
        assert "security-reader" in BUILT_IN_ROLE_IDS
        assert "admin" in BUILT_IN_ROLE_IDS

    def test_reader_role_permissions(self):
        """Reader role has correct permissions."""
        reader = next(r for r in BUILT_IN_ROLES if r.id == "reader")
        assert reader.built_in is True
        assert len(reader.permissions) >= 1

        # Should allow read/query on non-sensitive
        perm = reader.permissions[0]
        assert Action.READ in perm.actions
        assert perm.resource.sensitive is False

    def test_security_reader_inherits(self):
        """Security reader inherits from reader."""
        sec_reader = next(r for r in BUILT_IN_ROLES if r.id == "security-reader")
        assert "reader" in sec_reader.inherits_from

    def test_admin_has_full_access(self):
        """Admin role has full access."""
        admin = next(r for r in BUILT_IN_ROLES if r.id == "admin")
        # Should have all actions on at least one permission
        all_actions = set(Action)
        for perm in admin.permissions:
            if set(perm.actions) == all_actions:
                assert True
                return
        pytest.fail("Admin should have a permission with all actions")


class TestMemoryStore:
    """Test in-memory RBAC store."""

    @pytest.fixture
    def store(self):
        """Create a fresh memory store."""
        return RBACMemoryStore()

    def test_built_in_roles_loaded(self, store):
        """Built-in roles are loaded on init."""
        roles = store.list_roles()
        role_ids = {r.id for r in roles}
        assert "reader" in role_ids
        assert "admin" in role_ids

    def test_get_role(self, store):
        """Get a role by ID."""
        role = store.get_role("reader")
        assert role is not None
        assert role.id == "reader"

    def test_save_custom_role(self, store):
        """Save a custom role."""
        custom = Role(
            id="custom-role",
            name="Custom Role",
            description="Test role",
            permissions=[],
        )
        store.save_role(custom)

        retrieved = store.get_role("custom-role")
        assert retrieved is not None
        assert retrieved.name == "Custom Role"

    def test_cannot_delete_builtin(self, store):
        """Cannot delete built-in roles."""
        result = store.delete_role("reader")
        assert result is False
        assert store.get_role("reader") is not None

    def test_save_binding(self, store):
        """Save and retrieve a role binding."""
        binding = RoleBinding(
            id="test-binding",
            principal_id="test-user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
        )
        store.save_binding(binding)

        retrieved = store.get_binding("test-binding")
        assert retrieved is not None
        assert retrieved.principal_id == "test-user"

    def test_list_bindings_filter(self, store):
        """List bindings with filters."""
        store.save_binding(RoleBinding(
            id="binding1",
            principal_id="user1",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
        ))
        store.save_binding(RoleBinding(
            id="binding2",
            principal_id="user2",
            principal_type=PrincipalType.USER,
            role_id="admin",
            created_by="test",
        ))

        reader_bindings = store.list_bindings(role_id="reader")
        assert len(reader_bindings) == 1
        assert reader_bindings[0].principal_id == "user1"

    def test_get_roles_for_principal(self, store):
        """Get roles assigned to a principal."""
        store.save_binding(RoleBinding(
            id="binding",
            principal_id="test-user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
        ))

        roles = store.get_roles_for_principal(
            "test-user",
            PrincipalType.USER,
        )
        assert len(roles) == 1
        assert roles[0].id == "reader"

    def test_role_inheritance(self, store):
        """Role inheritance is resolved."""
        # security-reader inherits from reader
        store.save_binding(RoleBinding(
            id="binding",
            principal_id="test-user",
            principal_type=PrincipalType.USER,
            role_id="security-reader",
            created_by="test",
        ))

        roles = store.get_roles_for_principal(
            "test-user",
            PrincipalType.USER,
        )
        role_ids = {r.id for r in roles}
        assert "security-reader" in role_ids
        assert "reader" in role_ids  # Inherited


class TestEnforcer:
    """Test RBAC enforcer."""

    @pytest.fixture
    def store(self):
        """Create a store with test bindings."""
        store = RBACMemoryStore()
        # Grant reader to test-user
        store.save_binding(RoleBinding(
            id="user-reader",
            principal_id="test-user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
        ))
        # Grant security-reader to sec-user
        store.save_binding(RoleBinding(
            id="sec-user-binding",
            principal_id="sec-user",
            principal_type=PrincipalType.USER,
            role_id="security-reader",
            created_by="test",
        ))
        return store

    @pytest.fixture
    def enforcer(self, store):
        """Create enforcer with test store."""
        return RBACEnforcer(store=store)

    def test_check_access_allowed(self, enforcer):
        """Check access returns allow for permitted action."""
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="infrastructure",
            sensitive=False,
        )
        decision = enforcer.check_access(
            "test-user",
            PrincipalType.USER,
            resource,
            Action.READ,
        )
        assert decision.decision == PolicyDecision.ALLOW
        assert decision.matched_role == "reader"

    def test_check_access_denied_no_role(self, enforcer):
        """Check access returns deny for user without roles."""
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="infrastructure",
        )
        decision = enforcer.check_access(
            "unknown-user",
            PrincipalType.USER,
            resource,
            Action.READ,
        )
        assert decision.decision == PolicyDecision.DENY
        assert "No roles assigned" in decision.denial_reason

    def test_check_access_denied_sensitive(self, enforcer):
        """Reader cannot access sensitive resources."""
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
        )
        decision = enforcer.check_access(
            "test-user",
            PrincipalType.USER,
            resource,
            Action.READ,
        )
        assert decision.decision == PolicyDecision.DENY
        assert "sensitive" in decision.denial_reason.lower()

    def test_security_reader_can_access_sensitive(self, enforcer):
        """Security reader can access sensitive resources."""
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
        )
        decision = enforcer.check_access(
            "sec-user",
            PrincipalType.USER,
            resource,
            Action.READ,
        )
        assert decision.decision == PolicyDecision.ALLOW

    def test_require_access_raises(self, enforcer):
        """require_access raises on denial."""
        resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
        )
        with pytest.raises(AccessDeniedError) as exc_info:
            enforcer.require_access(
                "test-user",
                PrincipalType.USER,
                resource,
                Action.READ,
            )
        assert exc_info.value.decision.decision == PolicyDecision.DENY

    def test_filter_by_permission(self, enforcer):
        """Filter items by permission."""
        items = [
            {"id": "infra", "sensitive": False},
            {"id": "security", "sensitive": True},
            {"id": "workflow", "sensitive": False},
        ]

        def get_resource(item):
            return Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id=item["id"],
                sensitive=item["sensitive"],
            )

        allowed, filtered = enforcer.filter_by_permission(
            "test-user",
            PrincipalType.USER,
            items,
            get_resource,
            Action.READ,
        )

        assert len(allowed) == 2
        assert filtered == 1
        allowed_ids = {i["id"] for i in allowed}
        assert "security" not in allowed_ids


class TestPrincipalResolver:
    """Test principal resolution."""

    def test_from_agent_context(self):
        """Resolve from agent context."""
        principal = PrincipalResolver.from_agent_context(
            agent_id="claude-code",
            session_id="session-123",
        )
        assert principal.principal_type == PrincipalType.AGENT
        assert principal.agent_id == "claude-code"
        assert principal.session_id == "session-123"

    def test_from_cli_context_default(self, monkeypatch):
        """Resolve from CLI with default USER."""
        monkeypatch.delenv("CONTEXTCORE_USER", raising=False)
        monkeypatch.delenv("CONTEXTCORE_AGENT_ID", raising=False)
        monkeypatch.setenv("USER", "testuser")

        principal = PrincipalResolver.from_cli_context()
        assert principal.principal_type == PrincipalType.USER
        assert principal.id == "testuser"

    def test_from_cli_context_agent_mode(self, monkeypatch):
        """Resolve from CLI in agent mode."""
        monkeypatch.setenv("CONTEXTCORE_AGENT_ID", "my-agent")

        principal = PrincipalResolver.from_cli_context()
        assert principal.principal_type == PrincipalType.AGENT
        assert principal.id == "my-agent"


class TestRoleBinding:
    """Test role binding behavior."""

    def test_binding_expiration(self):
        """Expired bindings are detected."""
        binding = RoleBinding(
            id="test",
            principal_id="user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert binding.is_expired() is True

    def test_binding_not_expired(self):
        """Active bindings are not expired."""
        binding = RoleBinding(
            id="test",
            principal_id="user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert binding.is_expired() is False

    def test_binding_no_expiration(self):
        """Bindings without expiration never expire."""
        binding = RoleBinding(
            id="test",
            principal_id="user",
            principal_type=PrincipalType.USER,
            role_id="reader",
            created_by="test",
        )
        assert binding.is_expired() is False
