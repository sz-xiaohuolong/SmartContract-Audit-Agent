"""工程 MVP 的离线、确定性回归。"""
import unittest
from unittest.mock import patch

import mvp_runtime


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows
        self.name = None

    def build(self, name, payload):
        self.name = name
        self.rows = payload['rows']

    def read(self, name):
        if name != self.name:
            raise ValueError('集合不存在')
        return self.rows

    def search(self, name, query, limit):
        if name != self.name:
            raise ValueError('集合不存在')
        return [{'id': row['id'], 'distance': 1.0} for row in self.rows[:limit]]


class MvpRuntimeTest(unittest.TestCase):
    def test_embedding_is_deterministic_and_normalized(self):
        first = mvp_runtime.embed('function claimRewards address sender')
        self.assertEqual(first, mvp_runtime.embed('function claimRewards address sender'))
        self.assertEqual(len(first), 128)
        self.assertAlmostEqual(sum(value * value for value in first), 1, places=5)
        with self.assertRaises(ValueError):
            mvp_runtime.embed('   ')

    def test_snapshot_only_activates_after_complete_readback(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        docs = [{'id': 'one', 'document': {'id': 'one', 'text': 'a'}, 'vector': mvp_runtime.embed('a')},
                {'id': 'two', 'document': {'id': 'two', 'text': 'b'}, 'vector': mvp_runtime.embed('b')}]
        payload = {'purpose': 'ENGINEERING_MVP', 'researchEligible': False,
                   'embedding': {'dimension': 128}, 'rows': docs}
        class BrokenIndex(FakeIndex):
            def read(self, name):
                return self.rows[:1]
        with TemporaryDirectory() as directory, patch.object(mvp_runtime, 'candidate_payload', return_value=payload):
            store = Path(directory) / 'store'
            with self.assertRaises(ValueError):
                mvp_runtime.build(root=directory, store=store, index=BrokenIndex([]))
            self.assertFalse((store / 'active.json').exists())
            index = FakeIndex([])
            pointer = mvp_runtime.build(root=directory, store=store, index=index)
            self.assertEqual(pointer['documentCount'], 2)
            self.assertEqual(mvp_runtime.active(root=directory, store=store, index=index)[0], pointer)

    def test_context_never_exceeds_hard_limit(self):
        rows = []
        for number in range(3):
            rows.append({'id': str(number), 'document': {'id': str(number), 'role': 'VULNERABLE',
                         'groupId': 'g', 'text': 'contract A ' * 90}})
        index = FakeIndex(rows)
        index.name = 'mvp_' + 'a' * 32
        context, selected = mvp_runtime.select_context('contract A', {'collection': index.name}, {'rows': rows}, index)
        self.assertLessEqual(len(context.encode('utf-8')), 2048)
        self.assertEqual(selected, ['0', '1'])


if __name__ == '__main__':
    unittest.main()
