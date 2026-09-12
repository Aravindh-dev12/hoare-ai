from hoare.reviewer import quality_score
from hoare.rules import parse_rules_csv, retrieve_rules
from hoare.security import redact_secrets
from hoare.static_analysis import run_static_analysis


def test_sql_injection_static_finding():
    files = {'db.py': 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")'}
    findings = run_static_analysis(files)
    assert any(f.severity == 'critical' and 'SQL injection' in f.title for f in findings)


def test_secret_redaction():
    text, count = redact_secrets('api_key="abcdefghijklmnop"')
    assert count == 1
    assert 'abcdefghijklmnop' not in text


def test_rule_retrieval():
    rules = parse_rules_csv('id,type,description\n3,security,Never interpolate raw user input directly into SQL queries')
    matches = retrieve_rules(rules, {'x.py': 'sql = f"SELECT * FROM users WHERE id={user_input}"'})
    assert matches and matches[0]['id'] == '3'


def test_score_deterministic():
    findings = run_static_analysis({'db.py': 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")'})
    assert quality_score(findings) <= 8.1
