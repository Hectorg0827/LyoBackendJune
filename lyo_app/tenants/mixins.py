import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr
from typing import Optional

class TenantMixin:
    """
    Mixin to add organization awareness to models.
    Adds organization_id column and relationship.
    """
    
    @declared_attr
    def organization_id(cls) -> Mapped[Optional[int]]:
        # Nullable so tenant-scoped rows can exist before multi-tenancy is
        # activated (i.e. before any Organization is seeded). A hardcoded
        # default of 1 previously caused foreign-key violations whenever
        # org #1 didn't exist (e.g. inserting notification preferences).
        return mapped_column(
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=True,
            index=True,
            default=None,
        )

    @declared_attr
    def organization(cls) -> Mapped["Organization"]:
        # Use string forward reference to avoid circular imports
        return relationship("lyo_app.tenants.models.Organization")
