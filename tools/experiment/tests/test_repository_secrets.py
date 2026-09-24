"""防止源码再次包含形似真实凭证的硬编码字符串。"""
import re
import unittest
from pathlib import Path


class RepositorySecretsTest(unittest.TestCase):
    def test_java_sources_have_no_embedded_provider_keys(self):
        root = Path(__file__).resolve().parents[3]
        matches = []
        for directory in (root / 'src', root / 'audit-mvp'):
            for path in directory.rglob('*.java'):
                if re.search(r'sk-[A-Za-z0-9_-]{24,}', path.read_text(encoding='utf-8')):
                    matches.append(str(path.relative_to(root)))
        self.assertEqual([], matches)
