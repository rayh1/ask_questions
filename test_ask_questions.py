#!/usr/bin/env python3
"""Test suite for ask_questions.py

Tests spec parsing, validation, and key generation.
Run with: python3 test_ask_questions.py
"""

import json
import sys
import tempfile
from pathlib import Path

# Import the module to test
from ask_questions import (
    SpecError,
    Question,
    QuestionOption,
    parse_spec,
    parse_spec_content,
    load_spec_from_file,
    get_spec_json_schema,
    MAX_QUESTION_LENGTH,
    MAX_OPTION_LENGTH,
    MAX_QUESTIONS,
    MIN_MULTISELECT_OPTIONS,
    MAX_MULTISELECT_OPTIONS,
    KEY_PATTERN,
)


class SimpleTestRunner:
    """Simple test runner without external dependencies."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name):
        """Decorator to register a test."""

        def decorator(func):
            self.tests.append((name, func))
            return func

        return decorator

    def run(self):
        """Run all registered tests."""
        print(f"Running {len(self.tests)} tests...\n")

        for name, func in self.tests:
            try:
                func()
                self.passed += 1
                print(f"? {name}")
            except AssertionError as e:
                self.failed += 1
                print(f"? {name}")
                print(f"  {e}")
            except Exception as e:
                self.failed += 1
                print(f"? {name} (unexpected error)")
                print(f"  {type(e).__name__}: {e}")

        print(f"\n{'=' * 60}")
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("=" * 60)

        return 0 if self.failed == 0 else 1


# Create test runner
runner = SimpleTestRunner()


# Tests for parse_spec_content
@runner.test("parse_spec_content: Valid JSON")
def test_parse_spec_content_json():
    spec = parse_spec_content('{"test": "value"}', "test")
    assert spec == {"test": "value"}, f"Expected dict, got {spec}"


@runner.test("parse_spec_content: Valid YAML")
def test_parse_spec_content_yaml():
    try:
        spec = parse_spec_content("test: value", "test")
        assert spec == {"test": "value"}, f"Expected dict, got {spec}"
    except SpecError as e:
        # YAML might not be available
        if "pyyaml" not in str(e).lower():
            raise


@runner.test("parse_spec_content: Invalid content")
def test_parse_spec_content_invalid():
    try:
        parse_spec_content("{invalid json", "test")
        raise AssertionError("Should have raised SpecError")
    except SpecError:
        pass  # Expected


# Tests for parse_spec validation
@runner.test("parse_spec: Missing 'questions' key")
def test_parse_spec_no_questions():
    try:
        parse_spec({"other": "data"})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "questions" in str(e).lower()


@runner.test("parse_spec: 'questions' not a list")
def test_parse_spec_questions_not_list():
    try:
        parse_spec({"questions": "not a list"})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "list" in str(e).lower()


@runner.test("parse_spec: Missing question text")
def test_parse_spec_missing_question():
    try:
        parse_spec({"questions": [{"options": [{"value": "yes"}]}]})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "question" in str(e).lower()


@runner.test("parse_spec: Empty question text")
def test_parse_spec_empty_question():
    try:
        parse_spec({"questions": [{"question": "", "options": [{"value": "yes"}]}]})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "non-empty" in str(e).lower()


@runner.test("parse_spec: Options not a list")
def test_parse_spec_options_not_list():
    try:
        parse_spec({"questions": [{"question": "Test?", "options": "not a list"}]})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "list" in str(e).lower()


@runner.test("parse_spec: No options with explicit allow_freeform=False")
def test_parse_spec_no_options_no_freeform():
    # Explicitly setting allow_freeform to False with no options should error
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Test?", "options": [], "allow_freeform": False}
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "no options" in str(e).lower()


@runner.test("parse_spec: Option missing value")
def test_parse_spec_option_missing_value():
    try:
        parse_spec(
            {"questions": [{"question": "Test?", "options": [{"description": "desc"}]}]}
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "value" in str(e).lower()


@runner.test("parse_spec: Duplicate explicit keys")
def test_parse_spec_duplicate_keys():
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Q1?", "options": [{"value": "a"}], "key": "same"},
                    {"question": "Q2?", "options": [{"value": "b"}], "key": "same"},
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "duplicate" in str(e).lower()


@runner.test("parse_spec: Generated key conflicts with explicit")
def test_parse_spec_key_collision():
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Q1?",
                        "options": [{"value": "a"}],
                        "key": "question_1",
                    },
                    {"question": "Q2?", "options": [{"value": "b"}]},
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "conflicts" in str(e).lower() or "collision" in str(e).lower()


# Tests for valid specs
@runner.test("parse_spec: Valid minimal spec")
def test_parse_spec_valid_minimal():
    questions = parse_spec(
        {"questions": [{"question": "Test?", "options": [{"value": "yes"}]}]}
    )
    assert len(questions) == 1
    assert questions[0].question == "Test?"
    assert len(questions[0].options) == 1
    assert questions[0].options[0].value == "yes"


@runner.test("parse_spec: Valid with freeform only")
def test_parse_spec_freeform_only():
    questions = parse_spec(
        {"questions": [{"question": "Test?", "options": [], "allow_freeform": True}]}
    )
    assert len(questions) == 1
    assert questions[0].allow_freeform is True
    assert len(questions[0].options) == 0


@runner.test("parse_spec: allow_freeform defaults to True when no options")
def test_parse_spec_freeform_default_when_no_options():
    # When options is empty and allow_freeform is not specified, it should default to True
    questions = parse_spec({"questions": [{"question": "Test?", "options": []}]})
    assert len(questions) == 1
    assert questions[0].allow_freeform is True
    assert len(questions[0].options) == 0


@runner.test("parse_spec: allow_freeform defaults to False when options exist")
def test_parse_spec_freeform_default_when_options_exist():
    # When options exist and allow_freeform is not specified, it should default to False
    questions = parse_spec(
        {"questions": [{"question": "Test?", "options": [{"value": "a"}]}]}
    )
    assert len(questions) == 1
    assert questions[0].allow_freeform is False
    assert len(questions[0].options) == 1


@runner.test("parse_spec: Multiple questions with freeform-only and regular")
def test_parse_spec_mixed_freeform_and_options():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Comment?",
                    "options": [],
                },  # allow_freeform defaults to True
                {
                    "question": "Choose?",
                    "options": [{"value": "a"}, {"value": "b"}],
                },  # allow_freeform defaults to False
                {
                    "question": "Another comment?",
                    "options": [],
                    "key": "comment2",
                },  # allow_freeform defaults to True
            ]
        }
    )
    assert len(questions) == 3
    # First question: freeform only
    assert questions[0].allow_freeform is True
    assert len(questions[0].options) == 0
    # Second question: regular options
    assert questions[1].allow_freeform is False
    assert len(questions[1].options) == 2
    # Third question: freeform only with custom key
    assert questions[2].allow_freeform is True
    assert len(questions[2].options) == 0
    assert questions[2].key == "comment2"


@runner.test("parse_spec: Generated keys")
def test_parse_spec_generated_keys():
    questions = parse_spec(
        {
            "questions": [
                {"question": "Q1?", "options": [{"value": "a"}]},
                {"question": "Q2?", "options": [{"value": "b"}]},
                {"question": "Q3?", "options": [{"value": "c"}], "key": "custom"},
            ]
        }
    )
    assert len(questions) == 3
    assert questions[0].key is None  # Will be "question_0" at runtime
    assert questions[1].key is None  # Will be "question_1" at runtime
    assert questions[2].key == "custom"


@runner.test("parse_spec: Custom freeform label")
def test_parse_spec_custom_freeform_label():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Test?",
                    "options": [],
                    "allow_freeform": True,
                    "freeform_label": "Custom label",
                }
            ]
        }
    )
    assert questions[0].freeform_label == "Custom label"


@runner.test("parse_spec: Default freeform label")
def test_parse_spec_default_freeform_label():
    questions = parse_spec(
        {"questions": [{"question": "Test?", "options": [], "allow_freeform": True}]}
    )
    from ask_questions import DEFAULT_FREEFORM_LABEL

    assert questions[0].freeform_label == DEFAULT_FREEFORM_LABEL


# Tests for load_spec_from_file
@runner.test("load_spec_from_file: Valid JSON file")
def test_load_spec_from_file_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"test": "value"}, f)
        temp_path = f.name

    try:
        spec = load_spec_from_file(temp_path)
        assert spec == {"test": "value"}
    finally:
        Path(temp_path).unlink()


@runner.test("load_spec_from_file: Valid YAML file")
def test_load_spec_from_file_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("test: value\n")
        temp_path = f.name

    try:
        try:
            spec = load_spec_from_file(temp_path)
            assert spec == {"test": "value"}
        except SpecError as e:
            # YAML might not be available
            if "pyyaml" not in str(e).lower():
                raise
    finally:
        Path(temp_path).unlink()


@runner.test("load_spec_from_file: File not found")
def test_load_spec_from_file_not_found():
    try:
        load_spec_from_file("/nonexistent/file.json")
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "not found" in str(e).lower()


@runner.test("load_spec_from_file: Invalid JSON")
def test_load_spec_from_file_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json")
        temp_path = f.name

    try:
        try:
            load_spec_from_file(temp_path)
            raise AssertionError("Should have raised SpecError")
        except SpecError as e:
            assert "parse" in str(e).lower() or "json" in str(e).lower()
    finally:
        Path(temp_path).unlink()


# Test complex realistic spec
@runner.test("parse_spec: Complex realistic spec")
def test_parse_spec_complex():
    spec = {
        "questions": [
            {
                "question": "What is your favorite color?",
                "options": [
                    {"value": "Red", "description": "The color of passion"},
                    {"value": "Blue", "description": "The color of calm"},
                    {"value": "Green", "description": "The color of nature"},
                ],
                "allow_freeform": True,
                "freeform_label": "Other color",
                "key": "favorite_color",
            },
            {
                "question": "How many hours do you sleep?",
                "options": [
                    {"value": "< 6 hours"},
                    {"value": "6-8 hours"},
                    {"value": "> 8 hours"},
                ],
            },
            {
                "question": "Any comments?",
                "options": [],
            },  # allow_freeform defaults to True
        ]
    }

    questions = parse_spec(spec)
    assert len(questions) == 3
    assert questions[0].question == "What is your favorite color?"
    assert len(questions[0].options) == 3
    assert questions[0].allow_freeform is True
    assert questions[0].freeform_label == "Other color"
    assert questions[0].key == "favorite_color"

    assert questions[1].question == "How many hours do you sleep?"
    assert len(questions[1].options) == 3
    assert questions[1].key is None

    # Third question: freeform-only (no options)
    # This should trigger direct text input in ask_questions()
    assert questions[2].question == "Any comments?"
    assert len(questions[2].options) == 0
    assert questions[2].allow_freeform is True


# Tests for new validations (Recommendations)


@runner.test("parse_spec: Whitespace normalized in question text (Rec 4)")
def test_parse_spec_question_whitespace_normalized():
    questions = parse_spec(
        {"questions": [{"question": "  Test?  ", "options": [{"value": "a"}]}]}
    )
    assert questions[0].question == "Test?"


@runner.test("parse_spec: Question text too long (Rec 9)")
def test_parse_spec_question_too_long():
    long_question = "x" * (MAX_QUESTION_LENGTH + 1)
    try:
        parse_spec(
            {"questions": [{"question": long_question, "options": [{"value": "a"}]}]}
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "too long" in str(e).lower()


@runner.test("parse_spec: Option value too long (Rec 9)")
def test_parse_spec_option_too_long():
    long_value = "x" * (MAX_OPTION_LENGTH + 1)
    try:
        parse_spec(
            {"questions": [{"question": "Test?", "options": [{"value": long_value}]}]}
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "too long" in str(e).lower()


@runner.test("parse_spec: Option value must be non-empty (trimmed)")
def test_parse_spec_option_value_non_empty():
    try:
        parse_spec(
            {"questions": [{"question": "Test?", "options": [{"value": "   "}]}]}
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "non-empty" in str(e).lower()


@runner.test("parse_spec: Too many questions (Rec 12)")
def test_parse_spec_too_many_questions():
    questions = [
        {"question": f"Q{i}?", "options": [{"value": "a"}]}
        for i in range(MAX_QUESTIONS + 1)
    ]
    try:
        parse_spec({"questions": questions})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "too many" in str(e).lower()


@runner.test("parse_spec: Invalid key format - starts with number (Rec 15)")
def test_parse_spec_invalid_key_starts_with_number():
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [{"value": "a"}],
                        "key": "1invalid",
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "invalid key" in str(e).lower()


@runner.test("parse_spec: Invalid key format - contains spaces (Rec 15)")
def test_parse_spec_invalid_key_spaces():
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Test?", "options": [{"value": "a"}], "key": "my key"}
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "invalid key" in str(e).lower()


@runner.test("parse_spec: Invalid key format - contains special chars (Rec 15)")
def test_parse_spec_invalid_key_special_chars():
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Test?", "options": [{"value": "a"}], "key": "my-key"}
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "invalid key" in str(e).lower()


@runner.test("parse_spec: Valid key formats (Rec 15)")
def test_parse_spec_valid_key_formats():
    questions = parse_spec(
        {
            "questions": [
                {"question": "Q1?", "options": [{"value": "a"}], "key": "valid_key"},
                {
                    "question": "Q2?",
                    "options": [{"value": "b"}],
                    "key": "_starts_underscore",
                },
                {"question": "Q3?", "options": [{"value": "c"}], "key": "camelCase123"},
            ]
        }
    )
    assert questions[0].key == "valid_key"
    assert questions[1].key == "_starts_underscore"
    assert questions[2].key == "camelCase123"


@runner.test("parse_spec: Key must be string (Rec 15)")
def test_parse_spec_key_must_be_string():
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Test?", "options": [{"value": "a"}], "key": 123}
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'key' must be a string" in str(e).lower()


@runner.test("parse_spec: Description must be string (Rec 16)")
def test_parse_spec_description_must_be_string():
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [{"value": "a", "description": 123}],
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'description' must be a string" in str(e).lower()


@runner.test("parse_spec: allow_freeform must be boolean (Rec 7)")
def test_parse_spec_allow_freeform_must_be_boolean():
    try:
        parse_spec(
            {
                "questions": [
                    {"question": "Test?", "options": [], "allow_freeform": "true"}
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'allow_freeform' must be a boolean" in str(e).lower()


@runner.test("parse_spec: freeform_label validated (Rec 6)")
def test_parse_spec_freeform_label_validated():
    # Empty string should fail
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [],
                        "allow_freeform": True,
                        "freeform_label": "",
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'freeform_label' must be a non-empty string" in str(e).lower()

    # Only whitespace should fail
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [],
                        "allow_freeform": True,
                        "freeform_label": "   ",
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'freeform_label' must be a non-empty string" in str(e).lower()

    # Non-string should fail
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [],
                        "allow_freeform": True,
                        "freeform_label": 123,
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'freeform_label' must be a non-empty string" in str(e).lower()


@runner.test("parse_spec: freeform_label whitespace stripped (Rec 6)")
def test_parse_spec_freeform_label_stripped():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Test?",
                    "options": [],
                    "allow_freeform": True,
                    "freeform_label": "  Custom  ",
                }
            ]
        }
    )
    assert questions[0].freeform_label == "Custom"


@runner.test("parse_spec: Question text must be string type")
def test_parse_spec_question_must_be_string():
    try:
        parse_spec({"questions": [{"question": 123, "options": [{"value": "a"}]}]})
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'question' must be a string" in str(e).lower()


# Tests for multi_select feature


@runner.test("parse_spec: Valid multi_select with enough options")
def test_parse_spec_multiselect_valid():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Select features?",
                    "options": [{"value": "a"}, {"value": "b"}, {"value": "c"}],
                    "multi_select": True,
                }
            ]
        }
    )
    assert len(questions) == 1
    assert questions[0].multi_select is True
    assert len(questions[0].options) == 3


@runner.test("parse_spec: multi_select defaults to False")
def test_parse_spec_multiselect_default():
    questions = parse_spec(
        {"questions": [{"question": "Test?", "options": [{"value": "a"}]}]}
    )
    assert questions[0].multi_select is False


@runner.test("parse_spec: multi_select must be boolean")
def test_parse_spec_multiselect_must_be_boolean():
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [{"value": "a"}, {"value": "b"}],
                        "multi_select": "yes",
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert "'multi_select' must be a boolean" in str(e)


@runner.test("parse_spec: multi_select requires minimum options")
def test_parse_spec_multiselect_min_options():
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": [{"value": "a"}],  # Only 1 option
                        "multi_select": True,
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert f"at least {MIN_MULTISELECT_OPTIONS}" in str(e)


@runner.test("parse_spec: multi_select enforces maximum options")
def test_parse_spec_multiselect_max_options():
    too_many_options = [
        {"value": f"opt{i}"} for i in range(MAX_MULTISELECT_OPTIONS + 1)
    ]
    try:
        parse_spec(
            {
                "questions": [
                    {
                        "question": "Test?",
                        "options": too_many_options,
                        "multi_select": True,
                    }
                ]
            }
        )
        raise AssertionError("Should have raised SpecError")
    except SpecError as e:
        assert f"at most {MAX_MULTISELECT_OPTIONS}" in str(e)


@runner.test("parse_spec: multi_select with allow_freeform")
def test_parse_spec_multiselect_with_freeform():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Select features?",
                    "options": [{"value": "a"}, {"value": "b"}],
                    "multi_select": True,
                    "allow_freeform": True,
                    "freeform_label": "Other feature",
                }
            ]
        }
    )
    assert questions[0].multi_select is True
    assert questions[0].allow_freeform is True
    assert questions[0].freeform_label == "Other feature"


@runner.test("parse_spec: multi_select without allow_freeform")
def test_parse_spec_multiselect_without_freeform():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Select features?",
                    "options": [{"value": "a"}, {"value": "b"}],
                    "multi_select": True,
                    "allow_freeform": False,
                }
            ]
        }
    )
    assert questions[0].multi_select is True
    assert questions[0].allow_freeform is False


@runner.test("parse_spec: multi_select at boundary (min options)")
def test_parse_spec_multiselect_min_boundary():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Test?",
                    "options": [
                        {"value": f"opt{i}"} for i in range(MIN_MULTISELECT_OPTIONS)
                    ],
                    "multi_select": True,
                }
            ]
        }
    )
    assert questions[0].multi_select is True
    assert len(questions[0].options) == MIN_MULTISELECT_OPTIONS


@runner.test("parse_spec: multi_select at boundary (max options)")
def test_parse_spec_multiselect_max_boundary():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Test?",
                    "options": [
                        {"value": f"opt{i}"} for i in range(MAX_MULTISELECT_OPTIONS)
                    ],
                    "multi_select": True,
                }
            ]
        }
    )
    assert questions[0].multi_select is True
    assert len(questions[0].options) == MAX_MULTISELECT_OPTIONS


@runner.test("parse_spec: Complex spec with mixed single and multi_select")
def test_parse_spec_mixed_single_and_multiselect():
    questions = parse_spec(
        {
            "questions": [
                {
                    "question": "Single select?",
                    "options": [{"value": "a"}],
                    "key": "single",
                },
                {
                    "question": "Multi select?",
                    "options": [{"value": "x"}, {"value": "y"}, {"value": "z"}],
                    "multi_select": True,
                    "allow_freeform": True,
                    "key": "multi",
                },
                {
                    "question": "Freeform only?",
                    "options": [],
                    "key": "freeform",
                },
            ]
        }
    )
    assert len(questions) == 3
    assert questions[0].multi_select is False
    assert questions[1].multi_select is True
    assert questions[1].allow_freeform is True
    assert questions[2].multi_select is False
    assert questions[2].allow_freeform is True


@runner.test("schema: Matches runtime defaults for freeform-only")
def test_schema_allows_freeform_only_by_default():
    schema = get_spec_json_schema()
    question_schema = schema["properties"]["questions"]["items"]
    assert "allOf" in question_schema, "Expected schema to use allOf rules"

    # Must have rule: if allow_freeform is false => require options with minItems 1
    found_allow_freeform_rule = False
    for rule in question_schema.get("allOf", []):
        if rule.get("if", {}).get("properties", {}).get("allow_freeform") == {
            "const": False
        }:
            then = rule.get("then", {})
            assert "options" in then.get("required", [])
            assert then.get("properties", {}).get("options", {}).get("minItems") == 1
            found_allow_freeform_rule = True
    assert found_allow_freeform_rule, "Missing allow_freeform=false => options>=1 rule"

    # Ensure we no longer require allow_freeform=true when options is empty.
    # (Previously an anyOf forced allow_freeform const True or options minItems 1.)
    assert (
        "anyOf" not in question_schema
    ), "Schema should not force allow_freeform for empty options"


@runner.test("schema: Enforces multi_select option bounds")
def test_schema_enforces_multiselect_bounds():
    schema = get_spec_json_schema()
    question_schema = schema["properties"]["questions"]["items"]
    found_multiselect_rule = False
    for rule in question_schema.get("allOf", []):
        if rule.get("if", {}).get("properties", {}).get("multi_select") == {
            "const": True
        }:
            then = rule.get("then", {})
            assert "options" in then.get("required", [])
            options_schema = then.get("properties", {}).get("options", {})
            assert options_schema.get("minItems") == MIN_MULTISELECT_OPTIONS
            assert options_schema.get("maxItems") == MAX_MULTISELECT_OPTIONS
            found_multiselect_rule = True
    assert found_multiselect_rule, "Missing multi_select=true option bounds rule"


if __name__ == "__main__":
    sys.exit(runner.run())
