"""One explicitly approved API request. No retries, tools, or production feed writes."""
import json
import os
from pathlib import Path
import requests
from prepare_editorial_pilot import prepare, ARTICLES

def main():
    request_path = Path('/tmp/sneki-editorial-pilot-request.json')
    prepare(request_path)
    payload = json.loads(request_path.read_text(encoding='utf-8'))
    payload['store'] = False
    fields = ['id','assessment_status','title_de','summary','why_relevant','practice_example','next_step','limitations']
    properties = {field: {'type': 'string'} for field in fields}
    properties['assessment_status'] = {'type': 'string', 'enum': ['scored','insufficient_input']}
    payload['text'] = {'format': {'type': 'json_schema', 'name': 'editorial_pilot', 'strict': True,
        'schema': {'type': 'object', 'additionalProperties': False, 'required': ['items'],
            'properties': {'items': {'type': 'array', 'items': {'type': 'object',
                'additionalProperties': False, 'required': fields, 'properties': properties}}}}}}

    size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    conservative_cost = size * .25 / 1000000 + payload['max_output_tokens'] * 1.2 / 1000000
    if conservative_cost > .03:
        raise ValueError('Approved model cost budget exceeded before request')
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('Required existing API credential unavailable')
    # Exactly one POST: even a timeout or invalid result is not retried.
    response = requests.post('https://api.openai.com/v1/responses',
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        json=payload, timeout=180, allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f'Pilot API HTTP {response.status_code}; no retry performed')
    result = response.json()
    # Preserve usage before format validation so failure never loses the audit.
    Path('data/editorial-pilot-usage.json').write_text(json.dumps(result.get('usage', {})), encoding='utf-8')
    text = ''.join(part.get('text', '') for output in result.get('output', [])
                   if output.get('type') == 'message' for part in output.get('content', [])
                   if part.get('type') == 'output_text')
    generated = json.loads(text)
    items = generated.get('items', [])
    expected = {article[0] for article in ARTICLES}
    if len(items) != len(expected) or {item.get('id') for item in items} != expected:
        raise ValueError('Pilot result has missing or duplicate articles; no retry')
    fields = {'id','assessment_status','title_de','summary','why_relevant','practice_example','next_step','limitations'}
    for item in items:
        if set(item) != fields or not all(isinstance(value, str) for value in item.values()):
            raise ValueError('Invalid pilot article contract; no retry')
        if item['assessment_status'] not in {'scored','insufficient_input'}:
            raise ValueError('Invalid assessment status')
    usage = result.get('usage', {})
    cost = (usage.get('input_tokens', 0) * .20 + usage.get('output_tokens', 0) * 1.2) / 1000000
    output = dict(pilot=True, model=result.get('model'), usage=usage, model_cost_usd=cost,
                  conservative_budget_usd=.03, articles=[dict(id=a[0], source=a[1], published_at=a[2],
                  role=a[3], source_url=a[4]) for a in ARTICLES], items=items)
    target = Path('data/editorial-pilot-result.json')
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(api_calls=1, articles=len(items), model_cost_usd=cost,
                         input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'))))

if __name__ == '__main__':
    main()
