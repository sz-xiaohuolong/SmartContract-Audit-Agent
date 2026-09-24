"""本地 HTTP 夹具校验 REST 适配边界，不依赖真实 Milvus。"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from milvus_rest import MilvusRestIndex


class MilvusRestTest(unittest.TestCase):
    def test_search_checks_api_status_and_request_parameters(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path, body))
                response = {'code': 0, 'data': [{'id': 'known', 'distance': 1.0}]} if body['limit'] == 2 else {'code': 1100, 'message': '内部错误'}
                data = json.dumps(response).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            client = MilvusRestIndex('http://127.0.0.1:' + str(server.server_port))
            self.assertEqual([{'id': 'known', 'distance': 1.0}], client.search('s1b_' + 'a'*32, [1, 0], 2))
            self.assertEqual('/v2/vectordb/entities/search', seen[0][0])
            self.assertEqual('Strong', seen[0][1]['consistencyLevel'])
            self.assertEqual([[1, 0]], seen[0][1]['data'])
            with self.assertRaises(ValueError): client.search('s1b_' + 'a'*32, [1, 0], 3)
        finally: server.shutdown(); server.server_close(); thread.join()

    def test_rejects_remote_endpoints_and_legacy_collection_names(self):
        for url in ['http://example.com', 'http://user:secret@localhost:19530', 'http://localhost:19530/path']:
            with self.assertRaises(ValueError): MilvusRestIndex(url)
        with self.assertRaises(ValueError): MilvusRestIndex('http://127.0.0.1:1').search('legacy', [1, 0], 1)
