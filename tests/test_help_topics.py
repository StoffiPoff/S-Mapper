import json
import importlib


def test_help_topics_json_parses_and_has_core_sections():
    p = 'assets/help_topics.json'
    with open(p, 'r', encoding='utf8') as f:
        data = json.load(f)

    # Core sections always expected
    expected = ['Introduction', 'Mappings Tab', 'Macros', 'Ping Monitor', 'Low-Level Suppression', 'Best Practices']
    for k in expected:
        assert k in data, f"Help topic {k!r} is missing"