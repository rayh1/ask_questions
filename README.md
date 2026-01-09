# ask_questions

A CLI tool for asking questions interactively using [questionary](https://github.com/tmbo/questionary). Reads question specifications from JSON/YAML and outputs answers as JSON.

## Features

- **Single-select questions**: Pick one option from a list
- **Multi-select questions**: Checkbox-style selection of multiple options
- **Freeform input**: Allow custom text input (standalone or as "Other" option)
- **JSON/YAML specs**: Define questions in either format
- **JSON output**: Structured answers for easy parsing
- **Schema validation**: Built-in JSON Schema for spec validation

## Installation

```bash
pip install questionary pyyaml
```

Or using uv:

```bash
uv sync
```

## Usage

### Basic Usage

```bash
# From a file
python ask_questions.py --spec questions.yaml
python ask_questions.py --spec questions.json

# From stdin
cat questions.yaml | python ask_questions.py --spec -

# Pretty-print output
python ask_questions.py --spec questions.yaml --pretty

# Validate spec without asking questions
python ask_questions.py --spec questions.yaml --dry-run
```

### Utilities

```bash
# Print JSON Schema for spec format
python ask_questions.py --schema --pretty

# Print example spec
python ask_questions.py --example yaml
python ask_questions.py --example json
```

## Question Spec Format

### Quick-Start Templates

**1. Select only (menu):**
```yaml
questions:
  - question: "Pick one"
    options:
      - value: "A"
      - value: "B"
```

**2. Select OR freeform (menu includes an "Other" entry):**
```yaml
questions:
  - question: "Pick or type"
    options:
      - value: "A"
      - value: "B"
    allow_freeform: true
    freeform_label: "Other (type your own)"
```

**3. Freeform only (no menu; direct text input):**
```yaml
questions:
  - question: "Any notes?"
    options: []
    # allow_freeform defaults to true when options is empty
```

**4. Multiselect (checkbox-style, select multiple):**
```yaml
questions:
  - question: "Which features do you want?"
    options:
      - value: "Feature A"
      - value: "Feature B"
      - value: "Feature C"
    multi_select: true
    allow_freeform: true  # optional: adds "Other" for custom input
    freeform_label: "Other (type your own)"
```

### Spec Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | ✅ | - | Prompt shown to the user (max 500 chars) |
| `options` | array | ❌ | `[]` | List of option objects |
| `options[].value` | string | ✅ | - | Option value (max 200 chars) |
| `options[].description` | string | ❌ | `""` | Description shown under the option |
| `allow_freeform` | boolean | ❌ | `true` if options empty, else `false` | Allow custom text input |
| `freeform_label` | string | ❌ | `"Type something."` | Label for the freeform option |
| `multi_select` | boolean | ❌ | `false` | Enable checkbox-style multi-selection |
| `key` | string | ❌ | `"question_N"` | Output key identifier |

### Validation Rules

- Maximum 100 questions per spec
- Multi-select requires 2-15 options
- Keys must be valid identifiers (letters/numbers/underscore, starting with letter or underscore)
- Keys must be unique across questions
- If `allow_freeform` is false, at least one option is required

## Output Format

Outputs JSON to stdout:

```json
{
  "choice": "Option 1",
  "question_0": "Some value",
  "features": ["Feature A", "Feature C", "custom input"]
}
```

- Single-select questions return strings
- Multi-select questions return arrays of strings

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (invalid spec, missing file, etc.) |
| 130 | Cancelled by user (Ctrl+C) |

## Full Example

**questions.yaml:**
```yaml
questions:
  - question: "Pick an option"
    options:
      - value: "Option 1"
        description: "A predefined choice"
      - value: "Option 2"
        description: "Another predefined choice"
    key: choice

  - question: "Pick or type your own"
    options:
      - value: "A"
        description: "Short"
      - value: "B"
        description: "Also short"
    allow_freeform: true
    freeform_label: "Other (type your own)"
    key: choice_or_freeform

  - question: "Which features do you want?"
    options:
      - value: "Feature A"
        description: "First feature"
      - value: "Feature B"
        description: "Second feature"
      - value: "Feature C"
        description: "Third feature"
    multi_select: true
    allow_freeform: true
    freeform_label: "Other (type your own)"
    key: features

  - question: "Any comments?"
    options: []
    key: comments
```

**Run:**
```bash
python ask_questions.py --spec questions.yaml --pretty
```

**Output:**
```json
{
  "choice": "Option 1",
  "choice_or_freeform": "A",
  "features": ["Feature A", "Feature C"],
  "comments": "Looks good!"
}
```

## LLM / Generator Checklist

When generating specs programmatically:

- Always emit a top-level `questions` list
- For each question, satisfy at least one:
  - Provide a non-empty `options` list, OR
  - Set `allow_freeform: true` (or omit it when options is empty)
- Keep `key` values unique across questions
- Avoid using keys that start with `question_` unless you provide explicit keys for ALL questions

## Development

Open in VS Code with Dev Containers extension:

1. Open this folder in VS Code
2. Click "Reopen in Container" when prompted
3. Wait for container to build

### Running Tests

```bash
pytest
```

### Dependencies

- [questionary](https://github.com/tmbo/questionary) - Interactive CLI prompts
- [PyYAML](https://pyyaml.org/) - YAML parsing (optional, but recommended)
