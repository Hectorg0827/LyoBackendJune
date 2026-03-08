#!/usr/bin/env python3
"""Syntax check all Self-Evolution OS files."""
import py_compile
import sys

files = [
    'lyo_app/evolution/routes.py',
    'lyo_app/evolution/__init__.py',
    'lyo_app/events/__init__.py',
    'lyo_app/evolution/recommendation_engine.py',
    'lyo_app/events/processor.py',
    'lyo_app/relationship/__init__.py',
    'lyo_app/relationship/models.py',
    'lyo_app/relationship/schemas.py',
    'lyo_app/relationship/milestone_engine.py',
    'lyo_app/relationship/personality_adapter.py',
    'lyo_app/relationship/memory_system.py',
    'lyo_app/relationship/relationship_tracker.py',
    'lyo_app/relationship/routes.py',
    'lyo_app/personalization/cumulative_insights.py',
    'lyo_app/predictive/content_recommender.py',
    'lyo_app/proactive/ritual_builder.py',
    'lyo_app/proactive/routes.py',
    'lyo_app/predictive/routes.py',
    'lyo_app/enhanced_main.py',
]

errors = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        errors.append(str(e))

if errors:
    print('SYNTAX ERRORS:')
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print(f'All {len(files)} files pass syntax check ✅')
