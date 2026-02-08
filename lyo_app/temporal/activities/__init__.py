"""
Temporal Activities Module

Activities are the building blocks of workflows - each activity
wraps an existing agent method to make it durable and retriable.
"""

from .curriculum_activities import (
    generate_curriculum_activity,
    generate_lesson_activity,
    generate_learning_path_activity,
)

__all__ = [
    "generate_curriculum_activity",
    "generate_lesson_activity",
    "generate_learning_path_activity",
]
