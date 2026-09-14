"""Small, validated teaching tools shared by the native and web classrooms.

Manipulation is exploration, never a grading signal. The accompanying
checkpoint asks the learner to make a specific prediction or decision.
"""

import ast
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisualItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=240)


class VisualParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(pattern=r"^[a-wyzA-WYZ][a-zA-Z0-9_]{0,12}$")
    min: float = Field(ge=-10000, le=10000)
    max: float = Field(ge=-10000, le=10000)
    initial: float
    step: float = Field(default=1, gt=0, le=10000)

    @model_validator(mode="after")
    def bounded(self):
        if not self.min < self.max or not self.min <= self.initial <= self.max:
            raise ValueError("Parameter needs an ordered range and a value inside it")
        return self


class TeachingVisual(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    kind: Literal["fraction_bar", "comparison", "sequence", "graph"]
    title: str = Field(min_length=3, max_length=100)
    caption: str = Field(min_length=10, max_length=350)
    # An equivalent textual account remains available on older clients.
    description: str = Field(min_length=10, max_length=600)
    parts: int = Field(default=10, ge=2, le=20)
    whole: float = Field(default=1, gt=0, le=1000000)
    unit: str = Field(default="", max_length=40)
    value: int = Field(default=0, ge=0, le=20)
    entries: list[VisualItem] = Field(default_factory=list, max_length=6)
    expression: str = Field(default="", max_length=150)
    params: list[VisualParameter] = Field(default_factory=list, max_length=3)
    x_min: float = Field(default=-5, ge=-1000, le=1000)
    x_max: float = Field(default=5, ge=-1000, le=1000)
    # A fixed viewport makes changes in slope/scale visible during exploration.
    y_min: float = Field(default=-10, ge=-1000000, le=1000000)
    y_max: float = Field(default=10, ge=-1000000, le=1000000)

    @model_validator(mode="after")
    def useful_visual(self):
        if self.kind == "fraction_bar" and self.value > self.parts:
            raise ValueError("Shaded parts cannot exceed the whole")
        if self.kind in ("comparison", "sequence"):
            if len(self.entries) < 2 or self.value >= len(self.entries):
                raise ValueError("Provide at least two real examples or steps")
        if self.kind == "graph":
            if not self.expression or not self.params or self.x_min >= self.x_max or self.y_min >= self.y_max:
                raise ValueError("A graph needs an expression, parameters and ordered bounds")
            names = {p.name for p in self.params}
            functions = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs"}
            if len(names) != len(self.params) or names & (functions | {"x", "pi", "e"}):
                raise ValueError("Graph parameters must be distinct")
            tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", self.expression))
            allowed = names | {"x", "pi", "e"} | functions
            if tokens - allowed or re.search(r"[^a-zA-Z0-9_+*/^().\s-]", self.expression):
                raise ValueError("Only supported mathematical expressions are allowed")
            try:
                tree = ast.parse(self.expression.replace("^", "**"), mode="eval")
            except SyntaxError as exc:
                raise ValueError("Provide a complete mathematical expression") from exc
            permitted = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
                         ast.Div, ast.Pow, ast.UAdd, ast.USub, ast.Name, ast.Load, ast.Constant, ast.Call)
            for node in ast.walk(tree):
                if not isinstance(node, permitted):
                    raise ValueError("Unsupported mathematical operation")
                if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name)
                        or node.func.id not in functions or len(node.args) != 1 or node.keywords):
                    raise ValueError("Use a supported function with one argument")
        return self

    def update(self, payload: dict) -> bool:
        """Apply only bounded values belonging to this actual activity."""
        if not isinstance(payload, dict):
            return False
        if self.kind == "graph":
            values = payload.get("params")
            if not isinstance(values, dict) or set(values) != {p.name for p in self.params}:
                return False
            if any(isinstance(values[p.name], bool) or not isinstance(values[p.name], (float, int))
                   or not math.isfinite(values[p.name]) or not p.min <= values[p.name] <= p.max
                   for p in self.params):
                return False
            for param in self.params:
                param.initial = values[param.name]
        else:
            value = payload.get("value")
            limit = self.parts if self.kind == "fraction_bar" else len(self.entries) - 1
            if type(value) is not int or not 0 <= value <= limit:
                return False
            self.value = value
        return True
