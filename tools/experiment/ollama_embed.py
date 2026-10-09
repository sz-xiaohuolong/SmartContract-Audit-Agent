"""仅经本机 Ollama 生成 Nomic 文档和查询向量，并记录实际输入截取。"""
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

from snapshots import vector32


MODEL = 'nomic-embed-text:latest'
DIMENSION = 768
DOCUMENT_PREFIX = 'search_document: '
QUERY_PREFIX = 'search_query: '


class ContextLengthError(ValueError):
    pass


class OllamaEncoder:
    def __init__(self, url='http://127.0.0.1:11434', model=MODEL, expected_digest=None, transport=None):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment):
            raise ValueError('Ollama 编码器仅接受本机无凭证地址')
        self.url = url.rstrip('/')
        self.model = model
        self.transport = transport or self._request
        tags = self.transport('/api/tags', None)
        matches = [row for row in tags.get('models', []) if row.get('name') == model]
        if len(matches) != 1 or not re.fullmatch(r'[0-9a-f]{64}', matches[0].get('digest', '')):
            raise ValueError('本机 Ollama 模型名称或摘要无效')
        row = matches[0]
        if row.get('details', {}).get('embedding_length') != DIMENSION:
            raise ValueError('本机 Nomic 向量维度不是 768')
        self.digest = row['digest']
        self.context_length = row.get('details', {}).get('context_length')
        if expected_digest is not None and self.digest != expected_digest:
            raise ValueError('本机 Ollama 模型摘要与知识快照不一致')

    def _request(self, path, payload):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.url + path, data=data,
            headers={'Content-Type': 'application/json'} if data is not None else {})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=120) as response:
                body = response.read(6_000_000)
        except urllib.error.HTTPError as error:
            reason = error.read(1024).decode('utf-8', errors='replace')
            if 'input length exceeds the context length' in reason:
                raise ContextLengthError('本机模型拒绝超过有效上下文的输入') from error
            raise ValueError('Ollama 编码请求失败') from error
        if len(body) >= 6_000_000:
            raise ValueError('Ollama 编码响应过大')
        return json.loads(body)

    def _one(self, text, prefix):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('嵌入文本不能为空')
        used = len(text)
        failed = None
        while True:
            try:
                data = self.transport('/api/embeddings', {'model': self.model,
                    'prompt': prefix + text[:used], 'options': {'num_ctx': 8192}})
                break
            except ContextLengthError:
                failed = used
                used = used * 3 // 4
                if used < 64:
                    raise ValueError('文本即使截短也超出 Ollama 模型窗口')
        if failed is not None:
            low, high = used, failed
            for _ in range(12):
                if high - low <= 32:
                    break
                middle = (low + high) // 2
                try:
                    data = self.transport('/api/embeddings', {'model': self.model,
                        'prompt': prefix + text[:middle], 'options': {'num_ctx': 8192}})
                    low = middle
                except ContextLengthError:
                    high = middle
            used = low
        values = vector32(data.get('embedding'), DIMENSION)
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isfinite(norm) or norm == 0:
            raise ValueError('Ollama 返回无效向量')
        return vector32([value / norm for value in values], DIMENSION), {
            'originalChars': len(text), 'embeddedChars': used, 'truncated': used != len(text)}

    def encode_document(self, text):
        return self._one(text, DOCUMENT_PREFIX)

    def encode_query(self, text):
        return self._one(text, QUERY_PREFIX)

    def __call__(self, texts):
        return [self.encode_query(text)[0] for text in texts]
