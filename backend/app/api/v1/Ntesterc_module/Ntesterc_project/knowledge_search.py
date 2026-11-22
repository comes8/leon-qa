"""Local keyword retrieval for Chinese requirements and API field names."""
import re

_STOP = {'如何', '怎么', '这个', '一个', '需要', '相关', '进行', '测试', '是否', '什么', '可以', '以及', '然后', '内容'}


def ranked_chunks(documents, query, limit):
    normalized = query.lower().strip()
    words = set(re.findall(r'[a-z0-9_][a-z0-9_.-]{1,}', normalized))
    for phrase in re.findall(r'[\u4e00-\u9fff]+', normalized):
        words.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    words -= _STOP
    ranked = []
    for document in documents:
        content = document.content or ''
        for offset in range(0, len(content), 1000):
            chunk = content[max(0, offset - 100):offset + 1200]
            lower = chunk.lower()
            title = document.title.lower()
            score = sum(2 + min(lower.count(word), 3) for word in words if word in lower)
            score += sum(5 for word in words if word in title)
            if normalized in lower:
                score += 30
            if score:
                ranked.append({'content': chunk, 'metadata': {
                    'document_id': document.id, 'document_title': document.title,
                    'chunk_index': offset // 1000, 'score': score,
                }})
    ranked.sort(key=lambda item: item['metadata']['score'], reverse=True)
    return ranked[:max(1, min(20, limit))]
