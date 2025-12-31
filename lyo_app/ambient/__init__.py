"""
Ambient Presence System

Makes Lyo always accessible without being intrusive:
- Quick access from anywhere in the app
- Contextual inline help
- Floating assistant widget support
"""

from .presence_manager import presence_manager
from .models import AmbientPresenceState, QuickAction

__all__ = ['presence_manager', 'AmbientPresenceState', 'QuickAction']
