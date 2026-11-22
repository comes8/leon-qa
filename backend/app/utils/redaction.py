"""Shared redaction for stored requests, reports and model inputs."""
import re
import json

SENSITIVE = re.compile(r'(api.?key|api.?secret|authorization|password|private.?key|signature|access.?token|refresh.?token|cookie|(?:^|[_-])(?:secret|token)(?:$|[_-]))', re.I)

def redact(value):
    if isinstance(value, dict):
        label = value.get('key') or value.get('name')
        if isinstance(label, str) and SENSITIVE.search(label) and 'value' in value:
            value = {**value, 'value': '[REDACTED]'}
        return {key: ('[REDACTED]' if SENSITIVE.search(str(key)) else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(('{', '[')):
            try:
                return json.dumps(redact(json.loads(value)), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        value = re.sub(r'(Bearer\s+)[A-Za-z0-9._~-]+', r'\1[REDACTED]', value, flags=re.I)
        value = re.sub(r'(sk-[A-Za-z0-9_-]{8,})', '[REDACTED]', value)
        return re.sub(r'([?&](?:signature|api_key|token|secret)=)[^&\s]*', r'\1[REDACTED]', value, flags=re.I)
    return value

