"""
Temporal Workflows Module

Workflows orchestrate activities into complete user flows.
They are durable - if the server crashes, workflows resume exactly where they left off.
"""

from .course_generation import CourseGenerationWorkflowV1

__all__ = ["CourseGenerationWorkflowV1"]
