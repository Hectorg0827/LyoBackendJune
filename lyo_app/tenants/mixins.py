import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from lyo_app.tenants.models import Organization

class TenantMixin:
    """
    Mixin to add organization awareness to models.
    Adds organization_id column and relationship.
    """
    
    @declared_attr
    def organization_id(cls) -> Mapped[int]:
        return mapped_column(
            sa.Integer, 
            sa.ForeignKey("organizations.id"), 
            nullable=False, 
            index=True,
            default=1  # Default to Lyo Inc just in case (though should be set explicitly)
        )

    @declared_attr
    def organization(cls) -> Mapped["Organization"]:
        # Use string forward reference to avoid circular imports
        return relationship("lyo_app.tenants.models.Organization")
