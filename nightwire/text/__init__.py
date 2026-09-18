"""Public contracts for first-class Community Text."""

from nightwire.text.domain import (
    TextLifecycle, TextMode, TextObject, TextProvenance, TextScopeKind,
)
from nightwire.text.service import TextObjectRepository, TextObjectService, TextValidationError

__all__ = [
    "TextLifecycle", "TextMode", "TextObject", "TextObjectRepository", "TextObjectService",
    "TextProvenance", "TextScopeKind", "TextValidationError",
]
