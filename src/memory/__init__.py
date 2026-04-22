"""Memory subsystems for agents."""

from memory.short_term import ShortTermMemory

_short_term: ShortTermMemory | None = None


def get_short_term_memory() -> ShortTermMemory:
    """Process-wide singleton ``ShortTermMemory`` instance."""
    global _short_term
    if _short_term is None:
        _short_term = ShortTermMemory()
    return _short_term
