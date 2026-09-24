"""本地 Milvus 2.6 REST 适配；只操作独立快照集合，不依赖额外 SDK。"""
import os
import re
import urllib.parse
import urllib.request
from storage import decode, encode


class MilvusRestIndex:
    def __init__(self, url, token_env='MILVUS_TOKEN'):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('本地适配仅接受无内嵌凭证的 loopback HTTP 地址')
        self.url = url.rstrip('/')
        self.token = os.environ.get(token_env)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, endpoint, payload):
        headers = {'Content-Type': 'application/json', 'Request-Timeout': '10'}
        if self.token: headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.url + '/v2/vectordb/' + endpoint, encode(payload), headers, method='POST')
        with self.opener.open(request, timeout=15) as response:
            data = response.read(16_777_217)
        if len(data) > 16_777_216: raise ValueError('Milvus 输出超出上限')
        result = decode(data)
        if not isinstance(result, dict) or result.get('code') != 0 or 'data' not in result:
            raise ValueError('Milvus 返回错误或无效响应')
        return result['data']

    @staticmethod
    def collection(name):
        if not isinstance(name, str) or not re.fullmatch(r's1b_[0-9a-f]{32}', name):
            raise ValueError('只允许操作独立快照集合')
        return name

    def build(self, collection, payload):
        self.collection(collection)
        if self.request('collections/has', {'collectionName': collection})['has']:
            raise ValueError('集合已存在，不允许覆盖')
        schema = {'autoID': False, 'enableDynamicField': False, 'fields': [
            {'fieldName': 'id', 'dataType': 'VarChar', 'isPrimary': True, 'elementTypeParams': {'max_length': '64'}},
            {'fieldName': 'vector', 'dataType': 'FloatVector', 'elementTypeParams': {'dim': str(payload['embedding']['dimension'])}},
            {'fieldName': 'payload', 'dataType': 'VarChar', 'elementTypeParams': {'max_length': '65535'}}]}
        self.request('collections/create', {'collectionName': collection, 'schema': schema,
            'indexParams': [{'fieldName': 'vector', 'indexName': 'vector_idx', 'indexType': 'AUTOINDEX', 'metricType': 'COSINE'}],
            'params': {'consistencyLevel': 'Strong'}})
        rows = [{'id': r['id'], 'vector': r['vector'], 'payload': encode(r['document']).decode()} for r in payload['rows']]
        for at in range(0, len(rows), 128):
            batch = rows[at:at + 128]
            result = self.request('entities/insert', {'collectionName': collection, 'data': batch})
            if result.get('insertCount') != len(batch): raise ValueError('Milvus 未完整插入')
        self.request('collections/load', {'collectionName': collection})

    def read(self, collection):
        self.collection(collection)
        offset = 0
        while True:
            rows = self.request('entities/query', {'collectionName': collection, 'filter': '',
                'outputFields': ['id', 'vector', 'payload'], 'limit': 256, 'offset': offset, 'consistencyLevel': 'Strong'})
            if not isinstance(rows, list): raise ValueError('Milvus 查询结果无效')
            for row in rows:
                yield {'id': row['id'], 'vector': row['vector'], 'document': decode(row['payload'])}
            if len(rows) < 256: break
            offset += len(rows)

    def search(self, collection, vector, limit):
        self.collection(collection)
        return self.request('entities/search', {'collectionName': collection, 'data': [vector], 'annsField': 'vector',
            'limit': limit, 'outputFields': ['id'], 'consistencyLevel': 'Strong',
            'searchParams': {'metricType': 'COSINE', 'params': {}}})
