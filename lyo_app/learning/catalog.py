"""Deterministic starter catalog installed during the production migration.

The catalog is data, not demo UI state: every client reads these rows from the
same ``courses`` and ``lessons`` tables.  The seeder intentionally uses a
synchronous SQLAlchemy connection so Alembic can run it before an app instance
starts.  Re-running it updates the canonical rows and never duplicates them.
"""

from __future__ import annotations

from datetime import datetime
import secrets
from typing import Any

import sqlalchemy as sa
from passlib.hash import pbkdf2_sha256
from sqlalchemy.engine import Connection


CATALOG_SOURCE = "lyo-starter-catalog"
CATALOG_VERSION = 1
CATALOG_INSTRUCTOR_EMAIL = "catalog@lyoai.app"
CATALOG_INSTRUCTOR_USERNAME = "lyo_catalog"


STARTER_COURSES: tuple[dict[str, Any], ...] = (
    {
        "slug": "learn-faster-with-lyo",
        "title": "Learn Faster with Lyo",
        "description": (
            "Build a learning system that turns clear goals, active recall, "
            "spaced repetition, and reflection into durable progress."
        ),
        "short_description": "A practical system for remembering more and studying with purpose.",
        "topic": "Learning Science",
        "difficulty_level": "beginner",
        "category": "Study Skills",
        "tags": ["learning", "memory", "study skills"],
        "estimated_duration_hours": 2.0,
        "is_featured": True,
        "lessons": (
            {
                "title": "Turn a Wish into a Learning Goal",
                "description": "Define an outcome you can recognize and measure.",
                "duration_minutes": 15,
                "content": (
                    "A useful learning goal describes what you will be able to do, not only what "
                    "you will read. Replace ‘learn Spanish’ with ‘hold a five-minute conversation "
                    "about my day without translating every sentence.’\n\n"
                    "Use this structure: action + topic + evidence + date. Example: ‘Explain the "
                    "three causes of inflation in my own words and answer five practice questions "
                    "with 80% accuracy by Friday.’\n\n"
                    "Practice: write one goal for something you genuinely want to learn. Ask Lyo to "
                    "turn it into a small first milestone and a realistic weekly schedule."
                ),
            },
            {
                "title": "Active Recall: Make Your Brain Retrieve",
                "description": "Replace passive review with retrieval practice.",
                "duration_minutes": 20,
                "content": (
                    "Recognition feels like learning, but retrieval proves it. After reading a short "
                    "section, close it and explain the idea from memory. Then compare your explanation "
                    "with the source and repair only the missing pieces.\n\n"
                    "Good retrieval prompts include: What is the main idea? Why does it matter? What "
                    "example would I give? How is it different from a similar concept?\n\n"
                    "Practice: study one page for five minutes, hide it, and write everything you can "
                    "remember. Turn your weak spots into three questions for your next review."
                ),
            },
            {
                "title": "Spaced Repetition without Cramming",
                "description": "Review at expanding intervals before knowledge disappears.",
                "duration_minutes": 20,
                "content": (
                    "Memory strengthens when a fact is retrieved after some forgetting has begun. A "
                    "simple starting rhythm is today, tomorrow, three days later, one week later, and "
                    "two weeks later. Hard ideas return sooner; easy ideas wait longer.\n\n"
                    "Keep reviews short. Try to answer before looking, grade honestly, and schedule the "
                    "next review based on difficulty. The goal is not to reread everything.\n\n"
                    "Practice: choose five ideas from this course and create a review date for each. "
                    "Ask Lyo to quiz you instead of showing the answers first."
                ),
            },
            {
                "title": "Build Your Personal Learning Loop",
                "description": "Combine planning, practice, feedback, and reflection.",
                "duration_minutes": 25,
                "content": (
                    "A repeatable learning loop has four moves: choose a small target, attempt it from "
                    "memory, get specific feedback, and adjust the next attempt. Progress comes from "
                    "the quality of this loop more than from the number of hours logged.\n\n"
                    "At the end of a session, record: what became easier, what is still confusing, and "
                    "the exact next action. This makes it easy to continue on any device.\n\n"
                    "Final task: design a seven-day learning loop with one measurable outcome, three "
                    "practice sessions, two reviews, and a short reflection."
                ),
            },
        ),
    },
    {
        "slug": "practical-spanish-everyday-life",
        "title": "Practical Spanish for Everyday Life",
        "description": (
            "Learn useful Spanish for introductions, cafés, directions, and short daily conversations "
            "through speaking-first practice."
        ),
        "short_description": "Speak useful Spanish from the first lesson.",
        "topic": "Spanish",
        "difficulty_level": "beginner",
        "category": "Languages",
        "tags": ["Spanish", "conversation", "language learning"],
        "estimated_duration_hours": 2.0,
        "is_featured": True,
        "lessons": (
            {
                "title": "Introduce Yourself Naturally",
                "description": "Use a simple pattern to begin a conversation.",
                "duration_minutes": 20,
                "content": (
                    "Start with four building blocks: ‘Hola, me llamo…’ (Hello, my name is…), ‘Soy de…’ "
                    "(I am from…), ‘Trabajo en…’ (I work in…), and ‘Mucho gusto’ (Nice to meet you).\n\n"
                    "A natural mini-dialogue is: ‘Hola, me llamo Ana. ¿Cómo te llamas?’ — ‘Me llamo "
                    "Luis. Mucho gusto.’ Say it aloud, then replace the names and details.\n\n"
                    "Practice: record a 20-second introduction. Ask Lyo to reply in Spanish and correct "
                    "only the one change that would make you sound more natural."
                ),
            },
            {
                "title": "Order at a Café",
                "description": "Ask politely for food, drinks, and the check.",
                "duration_minutes": 20,
                "content": (
                    "Use ‘Quisiera…’ for a polite request: ‘Quisiera un café con leche, por favor.’ Ask "
                    "about options with ‘¿Tiene…?’ and request the check with ‘La cuenta, por favor.’\n\n"
                    "Listen for common questions: ‘¿Algo más?’ means ‘Anything else?’ and ‘¿Para aquí o "
                    "para llevar?’ means ‘For here or to go?’\n\n"
                    "Practice: role-play a complete order with Lyo. Include one drink, one food item, a "
                    "follow-up question, and the check."
                ),
            },
            {
                "title": "Ask for and Understand Directions",
                "description": "Navigate with a small set of high-value phrases.",
                "duration_minutes": 20,
                "content": (
                    "Begin with ‘Disculpe, ¿dónde está…?’ Useful direction words are derecha (right), "
                    "izquierda (left), derecho (straight), cerca (near), and lejos (far).\n\n"
                    "Repeat the important part to confirm: ‘Entonces, sigo derecho y doblo a la "
                    "izquierda, ¿correcto?’ Confirmation is more useful than pretending you understood.\n\n"
                    "Practice: ask for directions to a pharmacy, station, or restaurant. Draw the route "
                    "you hear and compare it with the Spanish instructions."
                ),
            },
            {
                "title": "Keep a Short Conversation Going",
                "description": "Use follow-up questions and repair phrases.",
                "duration_minutes": 25,
                "content": (
                    "Conversation grows through follow-up questions: ‘¿Y tú?’ (And you?), ‘¿Por qué?’ "
                    "(Why?), and ‘¿Qué te gusta hacer?’ (What do you like to do?).\n\n"
                    "When you get lost, say ‘¿Puede repetir más despacio?’ or ‘¿Qué significa…?’ These "
                    "phrases keep the interaction alive and turn confusion into learning.\n\n"
                    "Final task: have a three-minute conversation with Lyo about your day. Use at least "
                    "two follow-up questions and one repair phrase."
                ),
            },
        ),
    },
    {
        "slug": "personal-finance-foundations",
        "title": "Personal Finance Foundations",
        "description": (
            "Create a clear money system for spending, saving, debt, credit, and the decisions that "
            "matter most."
        ),
        "short_description": "Build a practical plan for cash flow, savings, debt, and credit.",
        "topic": "Personal Finance",
        "difficulty_level": "beginner",
        "category": "Life Skills",
        "tags": ["money", "budget", "credit"],
        "estimated_duration_hours": 2.0,
        "is_featured": True,
        "lessons": (
            {
                "title": "See Your Real Monthly Cash Flow",
                "description": "Turn transactions into a decision-ready picture.",
                "duration_minutes": 20,
                "content": (
                    "Cash flow is income received minus money spent during the same period. Separate "
                    "fixed obligations, flexible essentials, goals, and optional spending. Irregular "
                    "expenses should be converted into a monthly amount.\n\n"
                    "Do not begin by judging every purchase. First build an accurate baseline from the "
                    "last 30 to 90 days. A plan based on guesses will fail even when your intentions are good.\n\n"
                    "Practice: total each category and identify the single change that would create the "
                    "largest monthly breathing room."
                ),
            },
            {
                "title": "Build an Emergency Buffer",
                "description": "Protect your plan from predictable surprises.",
                "duration_minutes": 20,
                "content": (
                    "An emergency fund prevents a repair, medical bill, or income interruption from "
                    "becoming expensive debt. Start with a reachable first target, then work toward "
                    "several months of essential expenses.\n\n"
                    "Keep emergency money liquid and separate from everyday spending. Automate a small "
                    "transfer after each paycheck so the decision happens once.\n\n"
                    "Practice: choose a first target, deadline, and automatic contribution. Calculate how "
                    "many pay periods it will take."
                ),
            },
            {
                "title": "Understand Debt and Credit",
                "description": "Compare borrowing costs and protect your credit profile.",
                "duration_minutes": 25,
                "content": (
                    "APR estimates the annual cost of borrowing, but minimum payments can hide how long "
                    "repayment takes. Compare balances, rates, required payments, and total interest—not "
                    "only the monthly payment.\n\n"
                    "Credit scores generally reward on-time payments, low revolving utilization, and a "
                    "stable history. Avoid opening accounts you do not need just to chase a small score change.\n\n"
                    "Practice: list each debt and compare the avalanche method (highest rate first) with "
                    "the snowball method (smallest balance first)."
                ),
            },
            {
                "title": "Create a 90-Day Money Plan",
                "description": "Turn priorities into scheduled actions.",
                "duration_minutes": 25,
                "content": (
                    "Choose no more than three priorities for the next 90 days: stabilize cash flow, "
                    "build a buffer, reduce expensive debt, or fund a near-term goal. Give each priority "
                    "a number, deadline, and automatic action.\n\n"
                    "Review once a week for ten minutes. Compare actual results with the plan, explain the "
                    "difference, and adjust the next week without abandoning the whole system.\n\n"
                    "Final task: write your three priorities and schedule the first transfer or payment today."
                ),
            },
        ),
    },
    {
        "slug": "python-from-zero",
        "title": "Python from Zero",
        "description": (
            "Learn the core ideas behind Python programs and finish with a small project you can explain "
            "and extend."
        ),
        "short_description": "Write your first useful Python program step by step.",
        "topic": "Python Programming",
        "difficulty_level": "beginner",
        "category": "Technology",
        "tags": ["Python", "coding", "programming"],
        "estimated_duration_hours": 3.0,
        "is_featured": True,
        "lessons": (
            {
                "title": "Values, Variables, and Output",
                "description": "Store information and make a program communicate.",
                "duration_minutes": 25,
                "content": (
                    "A variable gives a name to a value: `name = \"Maya\"` and `age = 24`. Python uses "
                    "types such as strings, integers, floats, and booleans to represent different kinds "
                    "of information.\n\n"
                    "Use `print()` to inspect a result. F-strings combine text and variables clearly: "
                    "`print(f\"Hello, {name}\")`.\n\n"
                    "Practice: create variables for a course name, number of lessons, and completion "
                    "status, then print one readable sentence using all three."
                ),
            },
            {
                "title": "Decisions and Repetition",
                "description": "Control what runs and how often it runs.",
                "duration_minutes": 30,
                "content": (
                    "An `if` statement chooses a path based on a condition. A loop repeats work over a "
                    "collection or until a condition changes. Indentation defines which lines belong "
                    "inside each block.\n\n"
                    "Example: `for score in scores:` can examine every score, while an `if score >= 80:` "
                    "condition can label strong results.\n\n"
                    "Practice: loop through five quiz scores and print whether each result needs review."
                ),
            },
            {
                "title": "Functions: Reusable Pieces of Logic",
                "description": "Package behavior behind a clear name.",
                "duration_minutes": 30,
                "content": (
                    "A function accepts inputs, performs work, and can return an output. Small functions "
                    "make a program easier to test, explain, and change.\n\n"
                    "Example: `def percent(correct, total): return correct / total * 100`. Choose names "
                    "that describe the result and handle invalid inputs deliberately.\n\n"
                    "Practice: write a function that accepts minutes studied and returns a friendly "
                    "progress message. Test it with at least three values."
                ),
            },
            {
                "title": "Mini Project: Study Session Tracker",
                "description": "Combine variables, loops, conditions, and functions.",
                "duration_minutes": 40,
                "content": (
                    "Build a small program that stores study sessions as subject-and-minutes pairs, "
                    "totals the time, and identifies the subject with the most practice.\n\n"
                    "Break the project into functions: add a session, calculate totals, and print a "
                    "summary. Start with hard-coded data, then add user input only after the core works.\n\n"
                    "Final task: explain each function in plain language and add one feature, such as a "
                    "daily goal or a warning when a subject has not been reviewed."
                ),
            },
        ),
    },
    {
        "slug": "critical-thinking-media-literacy",
        "title": "Critical Thinking and Media Literacy",
        "description": (
            "Evaluate claims, evidence, sources, and your own assumptions before deciding what to believe "
            "or share."
        ),
        "short_description": "A practical method for judging claims and online information.",
        "topic": "Critical Thinking",
        "difficulty_level": "intermediate",
        "category": "Thinking Skills",
        "tags": ["critical thinking", "media literacy", "research"],
        "estimated_duration_hours": 2.0,
        "is_featured": False,
        "lessons": (
            {
                "title": "Separate Claims from Evidence",
                "description": "Identify exactly what is being asserted and what supports it.",
                "duration_minutes": 20,
                "content": (
                    "A claim is a statement that could be true or false. Evidence is the information "
                    "offered to support it. Confidence should depend on the quality and relevance of the "
                    "evidence, not on how confidently the claim is delivered.\n\n"
                    "Ask: What precisely is the claim? What evidence would change my mind? Does the "
                    "evidence support this claim or only a related one?\n\n"
                    "Practice: take one headline and rewrite it as a testable claim. List the evidence you "
                    "would need before accepting it."
                ),
            },
            {
                "title": "Recognize Bias without Stopping the Analysis",
                "description": "Use bias as a question, not a dismissal.",
                "duration_minutes": 20,
                "content": (
                    "Everyone selects and interprets information through prior beliefs and incentives. "
                    "Finding bias does not automatically prove a conclusion false; it tells you where to "
                    "look more carefully.\n\n"
                    "Watch for confirmation bias, availability bias, motivated reasoning, and sampling "
                    "bias. Then return to the evidence and method.\n\n"
                    "Practice: identify one belief you hold strongly and write the strongest evidence "
                    "that could count against it."
                ),
            },
            {
                "title": "Evaluate a Source",
                "description": "Check origin, expertise, incentives, method, and corroboration.",
                "duration_minutes": 25,
                "content": (
                    "Trace information to its original source. Check who produced it, how the information "
                    "was gathered, what is missing, and whether independent sources agree. A polished "
                    "page is not evidence of a reliable method.\n\n"
                    "Prefer primary documents and transparent data when available. For technical claims, "
                    "look for qualified expertise and a method that others could inspect.\n\n"
                    "Practice: compare two sources making the same claim and explain which deserves more "
                    "confidence and why."
                ),
            },
            {
                "title": "Make a Calibrated Decision",
                "description": "Act with the confidence the evidence supports.",
                "duration_minutes": 25,
                "content": (
                    "Many decisions must be made before certainty is possible. State your confidence, "
                    "identify the cost of being wrong, and choose an action that can be revised when new "
                    "evidence arrives.\n\n"
                    "Use language such as likely, uncertain, or strongly supported instead of forcing "
                    "every conclusion into true or false.\n\n"
                    "Final task: analyze a current claim using claim, evidence, alternatives, confidence, "
                    "and next information needed."
                ),
            },
        ),
    },
    {
        "slug": "ai-literacy-for-work-and-learning",
        "title": "AI Literacy for Work and Learning",
        "description": (
            "Use generative AI effectively while verifying results, protecting private information, and "
            "keeping human judgment in charge."
        ),
        "short_description": "Prompt, verify, and use AI responsibly for real outcomes.",
        "topic": "Artificial Intelligence",
        "difficulty_level": "beginner",
        "category": "Technology",
        "tags": ["AI", "prompting", "digital literacy"],
        "estimated_duration_hours": 2.0,
        "is_featured": True,
        "lessons": (
            {
                "title": "Give AI a Clear Job",
                "description": "Describe the outcome, context, constraints, and format.",
                "duration_minutes": 20,
                "content": (
                    "A useful prompt explains what success looks like. Include the task, relevant context, "
                    "constraints, intended audience, and desired output format. Examples improve consistency.\n\n"
                    "Instead of ‘help with math,’ try: ‘Teach me how to solve a two-step linear equation. "
                    "Ask one question at a time, wait for my answer, and give a hint before the solution.’\n\n"
                    "Practice: rewrite one vague request using outcome, context, constraints, and format."
                ),
            },
            {
                "title": "Verify before You Trust",
                "description": "Treat fluent answers as drafts that require checking.",
                "duration_minutes": 20,
                "content": (
                    "Generative models predict plausible text; they do not guarantee truth. Verify names, "
                    "dates, quotations, calculations, and high-stakes advice against reliable sources.\n\n"
                    "Ask the model to state assumptions and uncertainty, but do not treat its citations as "
                    "verified until you open the original source.\n\n"
                    "Practice: choose one factual answer, identify three checkable claims, and verify each "
                    "independently."
                ),
            },
            {
                "title": "Use AI as a Learning Partner",
                "description": "Ask for retrieval, feedback, and adaptive practice.",
                "duration_minutes": 25,
                "content": (
                    "AI is most useful for learning when it makes you think. Ask for a diagnostic question, "
                    "a hint, a comparison, a counterexample, or a quiz that adapts to your answer.\n\n"
                    "Avoid outsourcing the final work before you have attempted it. Share your reasoning "
                    "and ask for targeted feedback on the first weak step.\n\n"
                    "Practice: have Lyo quiz you on a topic, explain why each wrong answer is tempting, and "
                    "schedule the weak concepts for review."
                ),
            },
            {
                "title": "Protect Privacy and Keep Accountability",
                "description": "Know what should not be shared or delegated.",
                "duration_minutes": 25,
                "content": (
                    "Do not paste passwords, private keys, confidential business information, protected "
                    "personal data, or material you are not authorized to share. Remove identifying details "
                    "and follow your organization’s rules.\n\n"
                    "Humans remain responsible for decisions and published work. Review for accuracy, bias, "
                    "tone, and unintended harm before acting.\n\n"
                    "Final task: create a personal checklist for what you will verify, what you will never "
                    "share, and which decisions always require human approval."
                ),
            },
        ),
    },
)


def _known_values(table: sa.Table, values: dict[str, Any]) -> dict[str, Any]:
    """Keep the seed compatible with additive legacy production schemas."""
    return {key: value for key, value in values.items() if key in table.c}


def _row_id(bind: Connection, table: sa.Table, *conditions: Any) -> int | None:
    return bind.execute(sa.select(table.c.id).where(*conditions)).scalar_one_or_none()


def _insert_and_find_id(
    bind: Connection,
    table: sa.Table,
    values: dict[str, Any],
    *lookup_conditions: Any,
) -> int:
    bind.execute(table.insert().values(**_known_values(table, values)))
    row_id = _row_id(bind, table, *lookup_conditions)
    if row_id is None:
        raise RuntimeError(f"Unable to locate inserted {table.name} row")
    return row_id


def seed_starter_catalog(bind: Connection) -> dict[str, int]:
    """Insert or refresh the shared starter catalog and return change counts."""
    required_tables = {"organizations", "users", "courses", "lessons"}
    available_tables = set(sa.inspect(bind).get_table_names())
    missing = sorted(required_tables - available_tables)
    if missing:
        raise RuntimeError(f"Starter catalog requires missing tables: {', '.join(missing)}")

    metadata = sa.MetaData()
    organizations = sa.Table("organizations", metadata, autoload_with=bind)
    users = sa.Table("users", metadata, autoload_with=bind)
    courses = sa.Table("courses", metadata, autoload_with=bind)
    lessons = sa.Table("lessons", metadata, autoload_with=bind)
    now = datetime.utcnow()

    organization_id = _row_id(bind, organizations, organizations.c.slug == "lyo-inc")
    if organization_id is None:
        organization_id = _insert_and_find_id(
            bind,
            organizations,
            {
                "name": "Lyo Inc",
                "slug": "lyo-inc",
                "plan_tier": "enterprise",
                "is_active": True,
                "contact_email": "support@lyoai.app",
                "monthly_api_calls": 0,
                "monthly_ai_tokens": 0,
                "created_at": now,
                "updated_at": now,
            },
            organizations.c.slug == "lyo-inc",
        )

    instructor_id = _row_id(bind, users, users.c.email == CATALOG_INSTRUCTOR_EMAIL)
    if instructor_id is None:
        instructor_id = _insert_and_find_id(
            bind,
            users,
            {
                "email": CATALOG_INSTRUCTOR_EMAIL,
                "username": CATALOG_INSTRUCTOR_USERNAME,
                # The plaintext is never retained and the account is inactive.
                # Keeping a valid hash also makes login attempts fail cleanly
                # instead of raising passlib's UnknownHashError.
                "hashed_password": pbkdf2_sha256.hash(secrets.token_urlsafe(64)),
                "first_name": "Lyo",
                "last_name": "Learning Team",
                "bio": "Official starter courses from Lyo.",
                "is_active": False,
                "is_verified": True,
                "is_superuser": False,
                "auth_provider": "system",
                "created_at": now,
                "updated_at": now,
            },
            users.c.email == CATALOG_INSTRUCTOR_EMAIL,
        )

    created_courses = 0
    created_lessons = 0
    for course_number, definition in enumerate(STARTER_COURSES):
        course_id = _row_id(
            bind,
            courses,
            courses.c.instructor_id == instructor_id,
            courses.c.title == definition["title"],
        )
        course_values = {
            "title": definition["title"],
            "description": definition["description"],
            "summary": definition["short_description"],
            "short_description": definition["short_description"],
            "topic": definition["topic"],
            "difficulty_level": definition["difficulty_level"],
            "category": definition["category"],
            "tags": definition["tags"],
            "estimated_duration_hours": definition["estimated_duration_hours"],
            "target_duration_hours": definition["estimated_duration_hours"],
            "status": "published",
            "is_published": True,
            "is_featured": definition["is_featured"],
            "generation_metadata": {
                "source": CATALOG_SOURCE,
                "version": CATALOG_VERSION,
                "slug": definition["slug"],
                "display_order": course_number,
            },
            "instructor_id": instructor_id,
            "organization_id": organization_id,
            "created_at": now,
            "updated_at": now,
            "published_at": now,
        }
        if course_id is None:
            course_id = _insert_and_find_id(
                bind,
                courses,
                course_values,
                courses.c.instructor_id == instructor_id,
                courses.c.title == definition["title"],
            )
            created_courses += 1
        else:
            course_update_values = {
                key: value for key, value in course_values.items() if key != "created_at"
            }
            bind.execute(
                courses.update()
                .where(courses.c.id == course_id)
                .values(**_known_values(courses, course_update_values))
            )

        for order_index, lesson_definition in enumerate(definition["lessons"], start=1):
            lesson_id = _row_id(
                bind,
                lessons,
                lessons.c.course_id == course_id,
                lessons.c.title == lesson_definition["title"],
            )
            lesson_values = {
                "title": lesson_definition["title"],
                "description": lesson_definition["description"],
                "summary": lesson_definition["description"],
                "content": lesson_definition["content"],
                "content_type": "text",
                "course_id": course_id,
                "order_index": order_index,
                "duration_minutes": lesson_definition["duration_minutes"],
                "estimated_duration_minutes": float(lesson_definition["duration_minutes"]),
                "topic": definition["topic"],
                "tags": definition["tags"],
                "is_published": True,
                "is_preview": order_index == 1,
                "organization_id": organization_id,
                "created_at": now,
                "updated_at": now,
            }
            if lesson_id is None:
                _insert_and_find_id(
                    bind,
                    lessons,
                    lesson_values,
                    lessons.c.course_id == course_id,
                    lessons.c.title == lesson_definition["title"],
                )
                created_lessons += 1
            else:
                lesson_update_values = {
                    key: value for key, value in lesson_values.items() if key != "created_at"
                }
                bind.execute(
                    lessons.update()
                    .where(lessons.c.id == lesson_id)
                    .values(**_known_values(lessons, lesson_update_values))
                )

    return {"courses": created_courses, "lessons": created_lessons}


def remove_starter_catalog(bind: Connection) -> None:
    """Remove only rows owned by the dedicated catalog system account."""
    available_tables = set(sa.inspect(bind).get_table_names())
    if not {"users", "courses", "lessons"}.issubset(available_tables):
        return

    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=bind)
    courses = sa.Table("courses", metadata, autoload_with=bind)
    lessons = sa.Table("lessons", metadata, autoload_with=bind)
    instructor_id = _row_id(bind, users, users.c.email == CATALOG_INSTRUCTOR_EMAIL)
    if instructor_id is None:
        return

    course_ids = list(
        bind.execute(
            sa.select(courses.c.id).where(courses.c.instructor_id == instructor_id)
        ).scalars()
    )
    if course_ids:
        bind.execute(lessons.delete().where(lessons.c.course_id.in_(course_ids)))
        bind.execute(courses.delete().where(courses.c.id.in_(course_ids)))
