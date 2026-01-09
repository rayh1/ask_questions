#!/usr/bin/env python3
"""CLI wrapper for asking questions interactively using questionary.

Reads a question specification from JSON/YAML and outputs answers as JSON.

Usage:
        python ask_questions.py --spec questions.yaml
        python ask_questions.py --spec questions.json
        cat questions.yaml | python ask_questions.py --spec -
        python ask_questions.py --schema --pretty
        python ask_questions.py --example yaml

Quick-start templates
---------------------

1) Select only (menu):
        questions:
            - question: "Pick one"
                options:
                    - value: "A"
                    - value: "B"

2) Select OR freeform (menu includes an "Other" entry):
        questions:
            - question: "Pick or type"
                options:
                    - value: "A"
                    - value: "B"
                allow_freeform: true
                freeform_label: "Other (type your own)"

3) Freeform only (no menu; direct text input):
        questions:
            - question: "Any notes?"
                options: []
                # allow_freeform omitted -> defaults to true when options is empty

4) Multiselect (checkbox-style, select multiple):
        questions:
            - question: "Which features do you want?"
                options:
                    - value: "Feature A"
                    - value: "Feature B"
                    - value: "Feature C"
                multi_select: true
                allow_freeform: true  # optional: adds "Other" for custom input
                freeform_label: "Other (type your own)"

LLM / generator checklist
-------------------------

- Always emit a top-level "questions" list.
- For each question, satisfy at least one:
    - provide a non-empty "options" list, OR
    - set "allow_freeform: true" (or omit it when options is empty).
- Keep "key" values unique across questions.
- Avoid using keys that start with "question_" unless you provide explicit keys for ALL questions.
    (Otherwise you can collide with auto-generated keys like "question_0".)

Spec fields
-----------

- question (required): non-empty string
- options (optional; default []): list of {value (required), description (optional; default "")}
- allow_freeform (optional):
    - default: true if options is empty, false otherwise
    - if true with options: adds an extra menu entry labelled by freeform_label
    - if true without options: prompts directly for text input (no menu)
- freeform_label (optional; default "Type something."):
    - only used when options exist and allow_freeform is true
- multi_select (optional; default false):
    - if true: uses checkbox-style selection, user can pick multiple options
    - requires 2-15 options
    - output value is an array of selected values
    - if allow_freeform is true, includes an "Other" option for custom input
- key (optional): identifier for output key; if omitted, key is "question_N"

Key handling note
-----------------

If "key" is omitted in the spec, the output key is generated at ask-time as
"question_N" (based on question order). The parsed Question object keeps
Question.key as None in that case.

Rendering note
--------------

Option descriptions are shown under the option value as a second (indented) line.

Output format
-------------

Outputs JSON to stdout:
        {
                "my_question_key": "Option 1",
                "question_0": "Some value",
                "multi_select_key": ["Option A", "Option C", "custom input"]
        }

Note: multi_select questions return arrays; single-select questions return strings.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    import questionary
    from questionary import Choice
    from prompt_toolkit.styles import Style
    from prompt_toolkit.input import create_input
    from prompt_toolkit.output import create_output

    QUESTIONARY_AVAILABLE = True
except ImportError:
    QUESTIONARY_AVAILABLE = False


# Type-safe sentinel for freeform input
class _Sentinel(Enum):
    """Sentinel values for special cases."""

    FREEFORM = auto()


_FREEFORM_SENTINEL = _Sentinel.FREEFORM

# Default label for freeform input option
DEFAULT_FREEFORM_LABEL = "Type something."

# Validation limits
MAX_QUESTION_LENGTH = 500
MAX_OPTION_LENGTH = 200
MAX_QUESTIONS = 100
MIN_MULTISELECT_OPTIONS = 2
MAX_MULTISELECT_OPTIONS = 15

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CANCELLED = 130

# Key validation pattern
KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def get_example_spec() -> dict[str, Any]:
    return {
        "questions": [
            {
                "question": "Pick an option",
                "options": [
                    {"value": "Option 1", "description": "A predefined choice"},
                    {
                        "value": "Option 2",
                        "description": "Another predefined choice",
                    },
                ],
                "key": "choice",
            },
            {
                "question": "Pick or type your own",
                "options": [
                    {"value": "A", "description": "Short"},
                    {"value": "B", "description": "Also short"},
                ],
                "allow_freeform": True,
                "freeform_label": "Other (type your own)",
                "key": "choice_or_freeform",
            },
            {
                "question": "Which features do you want?",
                "options": [
                    {"value": "Feature A", "description": "First feature"},
                    {"value": "Feature B", "description": "Second feature"},
                    {"value": "Feature C", "description": "Third feature"},
                ],
                "multi_select": True,
                "allow_freeform": True,
                "freeform_label": "Other (type your own)",
                "key": "features",
            },
            {
                "question": "Any comments?",
                "options": [],
                "key": "comments",
            },
        ]
    }


def get_example_yaml() -> str:
    # Hand-authored YAML to avoid depending on PyYAML for printing examples.
    return (
        "questions:\n"
        '  - question: "Pick an option"\n'
        "    options:\n"
        '      - value: "Option 1"\n'
        '        description: "A predefined choice"\n'
        '      - value: "Option 2"\n'
        '        description: "Another predefined choice"\n'
        "    key: choice\n"
        '  - question: "Pick or type your own"\n'
        "    options:\n"
        '      - value: "A"\n'
        '        description: "Short"\n'
        '      - value: "B"\n'
        '        description: "Also short"\n'
        "    allow_freeform: true\n"
        '    freeform_label: "Other (type your own)"\n'
        "    key: choice_or_freeform\n"
        '  - question: "Which features do you want?"\n'
        "    options:\n"
        '      - value: "Feature A"\n'
        '        description: "First feature"\n'
        '      - value: "Feature B"\n'
        '        description: "Second feature"\n'
        '      - value: "Feature C"\n'
        '        description: "Third feature"\n'
        "    multi_select: true\n"
        "    allow_freeform: true\n"
        '    freeform_label: "Other (type your own)"\n'
        "    key: features\n"
        '  - question: "Any comments?"\n'
        "    options: []\n"
        "    # allow_freeform omitted -> defaults to true when options is empty\n"
        "    key: comments\n"
    )


def get_spec_json_schema() -> dict[str, Any]:
    # Notes:
    # - This schema focuses on structure and basic constraints.
    # - It cannot express key uniqueness or generated-key collision rules.
    question_schema: dict[str, Any] = {
        "type": "object",
        "required": ["question"],
        "additionalProperties": False,
        "properties": {
            "question": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_QUESTION_LENGTH,
                "description": "Prompt shown to the user.",
            },
            "options": {
                "type": "array",
                "default": [],
                "items": {
                    "type": "object",
                    "required": ["value"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_OPTION_LENGTH,
                        },
                        "description": {"type": "string", "default": ""},
                    },
                },
            },
            "allow_freeform": {
                "type": "boolean",
                "description": "Allow custom text input (see docs for default behavior).",
            },
            "freeform_label": {
                "type": "string",
                "default": DEFAULT_FREEFORM_LABEL,
                "minLength": 1,
            },
            "multi_select": {
                "type": "boolean",
                "default": False,
                "description": f"Enable checkbox-style multi-selection (requires {MIN_MULTISELECT_OPTIONS}-{MAX_MULTISELECT_OPTIONS} options).",
            },
            "key": {
                "type": "string",
                "pattern": KEY_PATTERN.pattern,
                "description": "Output key for this question (must be a valid identifier).",
            },
        },
        "allOf": [
            # Match runtime behavior:
            # - if allow_freeform is explicitly false, there must be at least one option
            {
                "if": {"properties": {"allow_freeform": {"const": False}}},
                "then": {
                    "required": ["options"],
                    "properties": {"options": {"type": "array", "minItems": 1}},
                },
            },
            # If multi_select is enabled, enforce option bounds
            {
                "if": {"properties": {"multi_select": {"const": True}}},
                "then": {
                    "required": ["options"],
                    "properties": {
                        "options": {
                            "type": "array",
                            "minItems": MIN_MULTISELECT_OPTIONS,
                            "maxItems": MAX_MULTISELECT_OPTIONS,
                        }
                    },
                },
            },
        ],
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ask_questions spec",
        "type": "object",
        "required": ["questions"],
        "additionalProperties": False,
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_QUESTIONS,
                "items": question_schema,
            }
        },
    }


class SpecError(Exception):
    """Exception raised for errors in question spec parsing or loading."""

    pass


@dataclass
class QuestionOption:
    """Represents an answer option for a question."""

    value: str
    description: str


@dataclass
class Question:
    """Represents a question with multiple choice options."""

    question: str
    options: list[QuestionOption]
    allow_freeform: bool = False
    key: Optional[str] = None  # Optional key to identify the answer in the results
    freeform_label: str = DEFAULT_FREEFORM_LABEL  # Label for freeform option
    multi_select: bool = False  # If True, allows selecting multiple options


def get_custom_style() -> Style:
    """Returns the questionary style configuration.

    Returns:
        Style object for questionary prompts
    """
    return Style(
        [
            ("qmark", "fg:#673ab7 bold"),  # Question mark
            ("question", "bold"),  # Question text
            ("pointer", "fg:#673ab7 bold"),  # Selection pointer
            ("highlighted", "fg:#673ab7 bold"),  # Selected option value
            ("selected", "fg:#cc5454"),  # Previously selected
            ("description", "fg:#888888"),  # Description text (gray)
        ]
    )


def ask_questions(
    questions: list[Question], prompt_input=None, prompt_output=None
) -> tuple[dict[str, str | list[str]], bool]:
    """
    Asks a series of questions and collects answers from the user.

    Each question is presented with its options, and the user selects one.
    If freeform is allowed, an additional "Type something" option is provided.
    If multi_select is enabled, user can select multiple options (checkbox-style).

    Args:
        questions: List of Question objects to ask
        prompt_input: prompt_toolkit Input object for reading user input (defaults to stdin)
        prompt_output: prompt_toolkit Output object for writing output (defaults to stdout)

    Returns:
        Tuple of (answers dict, was_cancelled bool)
        Dictionary mapping question keys (or indices) to selected answers.
        For multi_select questions, the value is a list of strings.
        Answers are returned in the order questions were asked (insertion order).

    Raises:
        ValueError: If questionary is not installed
    """
    if not QUESTIONARY_AVAILABLE:
        raise ValueError(
            "questionary not installed. Install with: pip install questionary"
        )

    answers: dict[str, str | list[str]] = {}
    custom_style = get_custom_style()

    # Ask each question sequentially
    for i, q in enumerate(questions):
        key = q.key if q.key else f"question_{i}"

        # Special case: no options, only freeform input
        # Skip the select menu and go directly to text input
        if len(q.options) == 0 and q.allow_freeform:
            try:
                text_kwargs = {"message": q.question}
                if prompt_input is not None:
                    text_kwargs["input"] = prompt_input
                if prompt_output is not None:
                    text_kwargs["output"] = prompt_output
                freeform_answer = questionary.text(**text_kwargs).ask()
                if freeform_answer is None:  # User cancelled
                    return answers, True
                answers[key] = freeform_answer
                continue  # Move to next question
            except (KeyboardInterrupt, EOFError):
                return answers, True

        # Build choices with title and description
        choices = []
        for option in q.options:
            # Use questionary's Choice with title and description
            title = [("class:highlighted", option.value)]
            description = option.description.strip()
            if description:
                title.append(("class:description", f"\n    {description}"))
            choices.append(
                Choice(
                    title=title,
                    value=option.value,
                )
            )

        # Add freeform option if allowed
        if q.allow_freeform:
            choices.append(
                Choice(
                    title=[
                        ("class:highlighted", q.freeform_label),
                    ],
                    value=_FREEFORM_SENTINEL,
                )
            )

        # Handle multiselect questions with checkbox
        if q.multi_select:
            try:
                checkbox_kwargs = {
                    "message": q.question,
                    "choices": choices,
                    "instruction": "(Space to select, Enter to confirm)",
                    "pointer": "›",
                    "style": custom_style,
                }
                if prompt_input is not None:
                    checkbox_kwargs["input"] = prompt_input
                if prompt_output is not None:
                    checkbox_kwargs["output"] = prompt_output

                selected_values = questionary.checkbox(**checkbox_kwargs).ask()

                # Handle cancellation (Ctrl+C)
                if selected_values is None:
                    return answers, True

                # Process selected values, handling freeform if present
                result_values: list[str] = []
                for val in selected_values:
                    if val is _FREEFORM_SENTINEL:
                        # Ask for freeform input
                        text_kwargs = {"message": "Enter your custom value:"}
                        if prompt_input is not None:
                            text_kwargs["input"] = prompt_input
                        if prompt_output is not None:
                            text_kwargs["output"] = prompt_output
                        freeform_answer = questionary.text(**text_kwargs).ask()
                        if freeform_answer is None:  # User cancelled
                            return answers, True
                        if freeform_answer:  # Only add non-empty freeform
                            result_values.append(freeform_answer)
                    elif isinstance(val, str):
                        result_values.append(val)

                answers[key] = result_values
                continue  # Move to next question

            except (KeyboardInterrupt, EOFError):
                return answers, True

        # Use questionary select to present the question (single-select)
        try:
            question_kwargs = {
                "message": q.question,
                "choices": choices,
                "use_shortcuts": False,  # Disable letter shortcuts
                "use_arrow_keys": True,
                "instruction": "",  # Remove instruction text
                "pointer": "›",  # Use a smaller pointer symbol
                "use_indicator": False,  # Disable indicator
                "style": custom_style,  # Apply custom styling
            }
            if prompt_input is not None:
                question_kwargs["input"] = prompt_input
            if prompt_output is not None:
                question_kwargs["output"] = prompt_output

            selected_value = questionary.select(**question_kwargs).ask()

            # Handle cancellation (Ctrl+C)
            if selected_value is None:
                return answers, True

            # If user selected freeform option, ask for text input
            if selected_value is _FREEFORM_SENTINEL and q.allow_freeform:
                text_kwargs = {"message": f"Enter your answer:"}
                if prompt_input is not None:
                    text_kwargs["input"] = prompt_input
                if prompt_output is not None:
                    text_kwargs["output"] = prompt_output
                freeform_answer = questionary.text(**text_kwargs).ask()
                if freeform_answer is None:  # User cancelled
                    return answers, True
                answers[key] = freeform_answer
            elif isinstance(selected_value, str):
                # Type guard to ensure only strings are assigned
                answers[key] = selected_value

        except (KeyboardInterrupt, EOFError):
            # User cancelled, return what we have so far
            return answers, True

    return answers, False


def parse_spec_content(content: str, source: str) -> dict[str, Any]:
    """Parse spec content as JSON or YAML.

    Args:
        content: The spec content as a string
        source: Description of the source (for error messages)

    Returns:
        Parsed spec as a dictionary

    Raises:
        SpecError: If content cannot be parsed as JSON or YAML
    """
    # Try JSON first
    try:
        return json.loads(content)
    except json.JSONDecodeError as json_error:
        if YAML_AVAILABLE:
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError as yaml_error:
                error_msg = f"Could not parse {source} as JSON or YAML.\n"
                error_msg += f"JSON error: {json_error}\n"
                error_msg += f"YAML error: {yaml_error}"
                if hasattr(yaml_error, "problem_mark"):
                    mark = yaml_error.problem_mark  # type: ignore
                    error_msg += f"\nYAML error at line {mark.line + 1}, column {mark.column + 1}"
                raise SpecError(error_msg)
        else:
            raise SpecError(f"Could not parse {source} as JSON: {json_error}")


def load_spec_from_file(file_path: str) -> dict[str, Any]:
    """Load question spec from JSON or YAML file.

    Args:
        file_path: Path to the spec file

    Returns:
        Parsed spec as a dictionary

    Raises:
        SpecError: If file cannot be read or parsed
    """
    path = Path(file_path)

    if not path.exists():
        raise SpecError(f"File not found: {file_path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(f"Failed to read file {file_path}: {e}")

    # Check for YAML-only file extensions
    if file_path.endswith((".yaml", ".yml")):
        if not YAML_AVAILABLE:
            raise SpecError("PyYAML not installed. Install with: pip install pyyaml")

    return parse_spec_content(content, file_path)


def load_spec_from_stdin() -> dict[str, Any]:
    """Load question spec from stdin.

    Returns:
        Parsed spec as a dictionary

    Raises:
        SpecError: If stdin is empty or content cannot be parsed
    """
    content = sys.stdin.read()

    if not content.strip():
        raise SpecError("No input provided on stdin")

    return parse_spec_content(content, "stdin")


def parse_spec(spec: dict[str, Any]) -> list[Question]:
    """Parse question spec into Question objects with comprehensive validation.

    Args:
        spec: The spec dictionary to parse

    Returns:
        List of Question objects

    Raises:
        SpecError: If spec validation fails
    """
    if not isinstance(spec, dict):
        raise SpecError("Spec must be an object (dictionary)")

    if "questions" not in spec:
        raise SpecError("Spec must contain 'questions' array")

    if not isinstance(spec["questions"], list):
        raise SpecError("'questions' must be a list")

    questions_data = spec["questions"]
    if len(questions_data) > MAX_QUESTIONS:
        raise SpecError(f"Too many questions (max {MAX_QUESTIONS})")

    questions: list[Question] = []
    seen_keys: set[str] = set()

    for i, q_dict in enumerate(questions_data):
        try:
            if not isinstance(q_dict, dict):
                raise SpecError(f"Question {i} must be an object (dictionary)")

            # Validate question text
            if "question" not in q_dict:
                raise SpecError(f"Missing 'question' field in question {i}")

            if not isinstance(q_dict["question"], str):
                raise SpecError(f"'question' must be a string in question {i}")

            question_text = q_dict["question"].strip()
            if not question_text:
                raise SpecError(
                    f"'question' must be a non-empty string in question {i}"
                )

            if len(question_text) > MAX_QUESTION_LENGTH:
                raise SpecError(
                    f"Question text too long (max {MAX_QUESTION_LENGTH} chars) in question {i}"
                )

            # Parse options
            options_data = q_dict.get("options", [])
            if not isinstance(options_data, list):
                raise SpecError(f"'options' must be a list in question {i}")

            options: list[QuestionOption] = []
            for j, opt_dict in enumerate(options_data):
                if not isinstance(opt_dict, dict):
                    raise SpecError(f"Option {j} must be a dict in question {i}")
                if "value" not in opt_dict:
                    raise SpecError(f"Option {j} missing 'value' in question {i}")
                if not isinstance(opt_dict["value"], str):
                    raise SpecError(
                        f"Option {j} 'value' must be a string in question {i}"
                    )

                option_value = opt_dict["value"].strip()
                if not option_value:
                    raise SpecError(
                        f"Option {j} 'value' must be a non-empty string in question {i}"
                    )
                if len(option_value) > MAX_OPTION_LENGTH:
                    raise SpecError(
                        f"Option {j} value too long (max {MAX_OPTION_LENGTH} chars) in question {i}"
                    )

                description = opt_dict.get("description", "")
                if not isinstance(description, str):
                    raise SpecError(
                        f"Option {j} 'description' must be a string in question {i}"
                    )

                options.append(
                    QuestionOption(
                        value=option_value,
                        description=description,
                    )
                )

            # Validate allow_freeform type and options
            # Default allow_freeform to True if options is empty
            if "allow_freeform" in q_dict:
                allow_freeform = q_dict["allow_freeform"]
                if not isinstance(allow_freeform, bool):
                    raise SpecError(
                        f"'allow_freeform' must be a boolean in question {i}"
                    )
            else:
                # Default: True if no options, False otherwise
                allow_freeform = len(options) == 0

            if not allow_freeform and len(options) == 0:
                raise SpecError(
                    f"Question {i} has no options and allow_freeform is false. "
                    f"Fix: add at least one option or set allow_freeform=true."
                )

            # Get and validate custom freeform label if provided
            freeform_label = q_dict.get("freeform_label", DEFAULT_FREEFORM_LABEL)
            if not isinstance(freeform_label, str) or not freeform_label.strip():
                raise SpecError(
                    f"'freeform_label' must be a non-empty string in question {i}"
                )
            freeform_label = freeform_label.strip()

            # Validate multi_select
            multi_select = q_dict.get("multi_select", False)
            if not isinstance(multi_select, bool):
                raise SpecError(f"'multi_select' must be a boolean in question {i}")

            if multi_select:
                if len(options) < MIN_MULTISELECT_OPTIONS:
                    raise SpecError(
                        f"'multi_select' requires at least {MIN_MULTISELECT_OPTIONS} options in question {i}"
                    )
                if len(options) > MAX_MULTISELECT_OPTIONS:
                    raise SpecError(
                        f"'multi_select' allows at most {MAX_MULTISELECT_OPTIONS} options in question {i}"
                    )

            # Validate key format and uniqueness
            key = q_dict.get("key")
            if key is not None:
                if not isinstance(key, str):
                    raise SpecError(f"'key' must be a string in question {i}")
                if not KEY_PATTERN.match(key):
                    raise SpecError(
                        f"Invalid key '{key}' in question {i}. Must be a valid identifier "
                        f"(letters/numbers/underscore, starting with a letter or underscore)."
                    )
                if key in seen_keys:
                    raise SpecError(
                        f"Duplicate key '{key}' found in question {i}. "
                        f"Fix: keys must be unique across questions."
                    )
                seen_keys.add(key)
            else:
                # Generate default key and check for collision
                default_key = f"question_{i}"
                if default_key in seen_keys:
                    raise SpecError(
                        f"Generated key '{default_key}' conflicts with explicit key. "
                        f"Fix: rename your explicit key(s) to avoid 'question_N' or provide keys for all questions."
                    )
                seen_keys.add(default_key)

            # Create Question object
            question = Question(
                question=question_text,
                options=options,
                allow_freeform=allow_freeform,
                key=key,
                freeform_label=freeform_label,
                multi_select=multi_select,
            )
            questions.append(question)
        except KeyError as e:
            raise SpecError(f"Missing required field {e} in question {i}")

    return questions


def main():
    parser = argparse.ArgumentParser(
        description="Ask questions from a spec file and output answers as JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--spec",
        help="Path to question spec file (JSON or YAML), or '-' to read from stdin",
    )
    mode_group.add_argument(
        "--schema",
        action="store_true",
        help="Print a JSON Schema for the spec format and exit",
    )
    mode_group.add_argument(
        "--example",
        choices=["yaml", "json"],
        help="Print an example spec and exit",
    )

    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Validate spec without asking questions"
    )

    args = parser.parse_args()

    # Helper functions are defined at module scope for reuse/testing.

    if args.dry_run and (args.schema or args.example is not None):
        parser.error("--dry-run can only be used together with --spec")

    if args.schema:
        schema = get_spec_json_schema()
        if args.pretty:
            print(json.dumps(schema, indent=2))
        else:
            print(json.dumps(schema))
        sys.exit(EXIT_SUCCESS)

    if args.example is not None:
        if args.example == "yaml":
            print(get_example_yaml(), end="")
        else:
            example = get_example_spec()
            if args.pretty:
                print(json.dumps(example, indent=2))
            else:
                print(json.dumps(example))
        sys.exit(EXIT_SUCCESS)

    try:
        # Load spec
        if args.spec == "-":
            spec = load_spec_from_stdin()
        else:
            spec = load_spec_from_file(args.spec)

        # Parse questions
        questions = parse_spec(spec)

        if not questions:
            raise SpecError("No questions found in spec")

        # Dry-run mode: validate and exit
        if args.dry_run:
            print(f"Valid spec with {len(questions)} questions", file=sys.stderr)
            sys.exit(EXIT_SUCCESS)

    except SpecError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    # Determine TTY device based on platform
    if platform.system() == "Windows":
        tty_device = "CON"
    else:
        tty_device = "/dev/tty"

    # Ask questions with proper resource management
    try:
        if args.spec == "-" or not sys.stdin.isatty():
            # Reading spec from stdin OR running without a TTY on stdin:
            # use the controlling terminal device for interactive input.
            try:
                with open(tty_device, "r", encoding="utf-8") as tty_input_file, open(
                    tty_device, "w", encoding="utf-8"
                ) as tty_output_file:
                    prompt_input = create_input(stdin=tty_input_file)
                    prompt_output = create_output(stdout=tty_output_file)
                    answers, was_cancelled = ask_questions(
                        questions,
                        prompt_input=prompt_input,
                        prompt_output=prompt_output,
                    )
            except OSError as e:
                print(
                    f"Error: Cannot open {tty_device} for interactive input: {e}",
                    file=sys.stderr,
                )
                print(
                    "This script requires an interactive terminal (TTY) for prompting",
                    file=sys.stderr,
                )
                sys.exit(EXIT_ERROR)
        else:
            # Interactive stdin is available; let questionary use defaults.
            answers, was_cancelled = ask_questions(questions)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled by user", file=sys.stderr)
        sys.exit(EXIT_CANCELLED)

    # Check if user cancelled
    if was_cancelled:
        print("\nCancelled by user", file=sys.stderr)
        sys.exit(EXIT_CANCELLED)

    # Output answers as JSON
    if args.pretty:
        print(json.dumps(answers, indent=2))
    else:
        print(json.dumps(answers))


if __name__ == "__main__":
    main()
