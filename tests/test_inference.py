from hoare.inference import extract_json_object


def test_extract_plain_json():
    assert extract_json_object('{"summary":"ok"}')['summary'] == 'ok'


def test_extract_json_after_thinking_and_fence():
    text = '<think>private reasoning</think>\n```json\n{"summary":"safe"}\n```'
    assert extract_json_object(text)['summary'] == 'safe'


def test_extract_json_from_surrounding_text():
    text = 'Result follows: {"summary":"ok","findings":[]} done'
    assert extract_json_object(text)['summary'] == 'ok'
