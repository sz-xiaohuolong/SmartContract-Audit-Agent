"""合成夹具计数器：每个 Unicode 码点计一个单元，不代表任何模型 tokenizer。"""
import json
import sys
payload = json.load(sys.stdin)
print(json.dumps({'tokens': len(payload['prompt'])}))
