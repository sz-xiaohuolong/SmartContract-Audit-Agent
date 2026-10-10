"""用真实受限程序事实检验 D2 的绑定、路径证据及三态语义。"""
import copy
import unittest

from d2_verify import evaluate
from program_facts import extract_facts


ACCESS = '''contract Vault {
  address owner;
  uint balance;
  function withdraw() public {
    require(msg.sender == owner);
    balance = 1;
  }
}'''

TAKEOVER = '''contract Vault {
  address owner;
  uint balance;
  function withdraw() public {
    owner = msg.sender;
  }
  function protectedWrite() public {
    require(msg.sender == owner);
    balance = 1;
  }
}'''


def reentrancy_source(before=False, write='balances[msg.sender] = 0;'):
    """可付款的公开入口建立余额，避免把不可达的初始状态当作攻击证据。"""
    call = 'msg.sender.call{value: balances[msg.sender]}("");'
    operations = [write, call] if before else [call, write]
    return '''contract Vault {
  mapping(address => uint) balances;
  function deposit() public payable { balances[msg.sender] = 1; }
  function withdraw() public {
    require(balances[msg.sender] == 1);
    %s
    %s
  }
}''' % tuple(operations)


class D2VerifyTest(unittest.TestCase):
    def case(self, source=ACCESS, mechanism='ACCESS_CONTROL', kind='WRITE'):
        facts = extract_facts(source)
        scope = next(s for s in facts['scopes'] if s['name'] == 'withdraw')
        risk = next(f for f in facts['facts'] if f['scope'] == scope['id'] and f['kind'] == kind)
        hypothesis = {'vulnerabilityType': mechanism, 'contract': 'Vault', 'function': 'withdraw',
                      'riskLine': risk['line'], 'riskOperation': kind, 'evidenceIds': [],
                      'sourceFile': 'Vault.sol'}
        return hypothesis, facts

    def tools(self, hypothesis, facts, check='protected-vars', status='OK'):
        return [{'engine': 'SLITHER', 'status': status, 'sourceHash': facts['sourceHash'],
                 'issues': [{'check': check, 'elements': [{
                     'type': 'function', 'name': hypothesis['function'],
                     'type_specific_fields': {'parent': {'type': 'contract', 'name': hypothesis['contract']}},
                     'source_mapping': {'lines': [hypothesis['riskLine']], 'filename_relative': 'Vault.sol'}
                 }]}]}]

    def assess(self, source=ACCESS, mechanism='ACCESS_CONTROL', kind='WRITE', tools=None):
        hypothesis, facts = self.case(source, mechanism, kind)
        return evaluate(hypothesis, facts, tools if tools is not None else self.tools(hypothesis, facts),
                        source=source)

    def obligations(self, result):
        return {item['name']: item for item in result['obligations']}

    def test_schema_and_unbound_legacy_input_are_unknown(self):
        result = evaluate({'riskLine': 10, 'function': 'withdraw', 'evidenceIds': []},
                          {'facts': []}, [{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
        self.assertEqual('2', result['schemaVersion'])
        self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual({'actor', 'resource', 'pre_risk_guard', 'entry_coverage', 'state_version', 'bypass'},
                         set(self.obligations(result)))
        self.assertTrue(all(item['reason'] for item in result['obligations']))

    def test_alert_without_program_path_does_not_support_hypothesis(self):
        result = evaluate({'riskLine': 10, 'function': 'withdraw', 'evidenceIds': []}, {'facts': []},
                          [{'engine': 'SLITHER', 'status': 'OK', 'issues': [
                              {'check': 'reentrancy-eth', 'elements': [{'source_mapping': {'lines': [10]}}]}]}])
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual([], result['references'])

    def test_source_hash_and_facts_must_bind_to_exact_source(self):
        hypothesis, facts = self.case()
        for changed in [dict(facts, sourceHash='0' * 64), dict(facts, facts=[]),
                        dict(facts, scopes=[dict(facts['scopes'][0], complete=False)])]:
            with self.subTest(facts=changed):
                result = evaluate(hypothesis, changed, self.tools(hypothesis, facts), source=ACCESS)
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertFalse(any(o['status'] == 'SUPPORTED' for o in result['obligations']))
        self.assertEqual('UNKNOWN', evaluate(hypothesis, facts, self.tools(hypothesis, facts))['verdict'])
        self.assertEqual('UNKNOWN', evaluate(dict(hypothesis, sourceHash='f' * 64), facts,
                                           self.tools(hypothesis, facts), source=ACCESS)['verdict'])

    def test_risk_binding_rejects_wrong_contract_function_line_kind_and_mechanism(self):
        hypothesis, facts = self.case()
        for patch in [{'contract': 'Other'}, {'function': 'deposit'}, {'riskLine': 5},
                      {'riskOperation': 'CALL'}, {'riskOperation': '任意写入'},
                      {'vulnerabilityType': 'REENTRANCY'}, {'mechanism': 'REENTRANCY'},
                      {'riskFactId': 'foreign'}, {'resource': 'owner'}]:
            with self.subTest(patch=patch):
                result = evaluate(dict(hypothesis, **patch), facts, self.tools(hypothesis, facts), source=ACCESS)
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual([], result['references'])

    def test_same_line_overloads_and_multiple_risks_are_ambiguous(self):
        for source in [
            'contract Vault { uint balance; function withdraw() public { balance = 1; balance = 2; } }',
            'contract Vault { uint balance; function withdraw() public { balance = 1; } function withdraw(uint a) public { balance = a; } }']:
            with self.subTest(source=source):
                result = self.assess(source)
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual([], result['references'])

    def test_complete_permission_block_has_opposite_verdicts(self):
        result = self.assess()
        self.assertEqual(('REFUTED', 'SUPPORTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual({'SUPPORTED'}, {item['status'] for item in result['obligations']})
        self.assertEqual('BLOCKED', result['pathEvidence']['status'])
        self.assertTrue(result['pathEvidence']['references'])

    def test_临时接管随后被覆盖不构成持久权限接管(self):
        source = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;').replace(
            'owner = msg.sender;', 'owner = msg.sender;\n    owner = trusted;')
        result = self.assess(source)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('UNKNOWN', result['protectionVerdict'])
        self.assertNotEqual('REACHABLE', result['pathEvidence']['status'])

    def test_修饰器后置覆盖权限不构成持久接管(self):
        source = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;').replace(
            'function withdraw() public {',
            'modifier reset() { _; owner = trusted; }\n  function withdraw() public reset {')
        result = self.assess(source)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('UNKNOWN', result['protectionVerdict'])
        self.assertNotEqual('REACHABLE', result['pathEvidence']['status'])

    def test_其他资源的后续写入不否定权限接管(self):
        source = TAKEOVER.replace('owner = msg.sender;', 'owner = msg.sender;\n    balance = 1;')
        result = self.assess(source)
        self.assertEqual(('SUPPORTED', 'REFUTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual('REACHABLE', result['pathEvidence']['status'])

    def test_接管之前的同资源写入不否定最终接管(self):
        source = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;').replace(
            'owner = msg.sender;', 'owner = trusted;\n    owner = msg.sender;')
        hypothesis, facts = self.case(source)
        hypothesis['riskLine'] = 7
        result = evaluate(hypothesis, facts, self.tools(hypothesis, facts), source=source)
        self.assertEqual(('SUPPORTED', 'REFUTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual('REACHABLE', result['pathEvidence']['status'])

    def test_消费入口检查前覆盖权限不能证明接管路径(self):
        source = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;').replace(
            'require(msg.sender == owner);', 'owner = trusted;\n    require(msg.sender == owner);')
        result = self.assess(source)
        self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_消费入口检查前外调不能证明接管路径(self):
        source = TAKEOVER.replace('require(msg.sender == owner);',
                                  'msg.sender.call("");\n    require(msg.sender == owner);')
        result = self.assess(source)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_消费入口附加不同权限或其他检查保持未知(self):
        base = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;')
        for checks in ('require(msg.sender == trusted);\n    require(msg.sender == owner);',
                       'require(msg.sender == owner);\n    require(msg.sender == trusted);',
                       'require(msg.sender == owner);\n    require(msg.sender == owner);',
                       'require(0 == 1);\n    require(msg.sender == owner);'):
            with self.subTest(checks=checks):
                result = self.assess(base.replace('require(msg.sender == owner);', checks))
                self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))
                self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_消费入口风险后的关门检查覆盖和额外外调保持未知(self):
        base = TAKEOVER.replace('address owner;', 'address owner;\n  address trusted;')
        for closing in ('require(0 == 1);',
                        'owner = trusted;\n    require(msg.sender == owner);',
                        'msg.sender.transfer(1);'):
            with self.subTest(closing=closing):
                result = self.assess(base.replace('balance = 1;', 'balance = 1;\n    ' + closing))
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual('UNKNOWN', result['pathEvidence']['status'])
        checks = 'require(msg.sender == owner);\n    owner = trusted;\n    require(msg.sender == owner);'
        result = self.assess(base.replace('require(msg.sender == owner);', checks))
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_消费入口必须公开完整且有检查后的实际风险(self):
        sources = [TAKEOVER.replace('protectedWrite() public', 'protectedWrite() ' + visibility)
                   for visibility in ('private', 'internal', '')]
        sources += [TAKEOVER.replace('balance = 1;', ''),
                    TAKEOVER.replace('balance = 1;', 'if (true) { balance = 1; }'),
                    TAKEOVER.replace('require(msg.sender == owner);\n    balance = 1;',
                                     'balance = 1;\n    require(msg.sender == owner);'),
                    TAKEOVER.replace('balance = 1;', 'owner = msg.sender;'),
                    TAKEOVER.replace('balance = 1;', '').replace(
                        '\n}', '\n  function internalWrite() private { balance = 1; }\n}')]
        for source in sources:
            with self.subTest(source=source):
                result = self.assess(source)
                self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))
                self.assertEqual('UNKNOWN', result['pathEvidence']['status'])

    def test_有效公开消费路径保留实际风险事实引用(self):
        for operation, kind in (('balance = 1;', 'WRITE'), ('msg.sender.call("");', 'CALL')):
            with self.subTest(kind=kind):
                source = TAKEOVER.replace('protectedWrite() public', 'protectedWrite() external').replace(
                    'balance = 1;', operation)
                hypothesis, facts = self.case(source)
                result = evaluate(hypothesis, facts, self.tools(hypothesis, facts), source=source)
                self.assertEqual(('SUPPORTED', 'REFUTED'), (result['verdict'], result['protectionVerdict']))
                self.assertEqual('REACHABLE', result['pathEvidence']['status'])
                consumer = next(s for s in facts['scopes'] if s['name'] == 'protectedWrite')
                operation_fact = next(f for f in facts['facts'] if f['scope'] == consumer['id'] and f['kind'] == kind)
                self.assertIn(operation_fact['id'], {ref['factId'] for ref in result['pathEvidence']['references']})

    def test_有效消费路径不引用其他私有入口(self):
        source = TAKEOVER.replace('\n}', '\n  function privateWrite() private { '
                                  'require(msg.sender == owner); balance = 2; }\n}')
        hypothesis, facts = self.case(source)
        result = evaluate(hypothesis, facts, self.tools(hypothesis, facts), source=source)
        self.assertEqual('SUPPORTED', result['verdict'])
        private_scope = next(s for s in facts['scopes'] if s['name'] == 'privateWrite')
        self.assertFalse(any(ref['scope'] == private_scope['id'] for ref in result['pathEvidence']['references']))

    def test_empty_alerts_are_not_the_reason_for_permission_refutation(self):
        _, facts = self.case()
        result = self.assess(tools=[{'engine': 'SLITHER', 'status': 'OK', 'issues': [], 'sourceHash': facts['sourceHash']}])
        self.assertEqual('REFUTED', result['verdict'])
        no_guard = self.assess(ACCESS.replace('require(msg.sender == owner);', ''),
                               tools=[{'engine': 'SLITHER', 'status': 'OK', 'issues': []}])
        self.assertEqual('UNKNOWN', no_guard['verdict'])

    def test_missing_and_failed_tools_keep_program_evidence_but_verdict_unknown(self):
        for tools in [[], [{'engine': 'SLITHER', 'status': 'TIMEOUT', 'issues': []}],
                      [{'engine': 'SLITHER', 'status': 'ERROR', 'issues': []}],
                      [{'engine': 'SLITHER', 'status': 'OK', 'issues': None}]]:
            with self.subTest(tools=tools):
                result = self.assess(tools=tools)
                self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))
                self.assertEqual('SUPPORTED', self.obligations(result)['pre_risk_guard']['status'])
                self.assertTrue(self.obligations(result)['pre_risk_guard']['references'])

    def test_partial_inheritance_alias_and_complex_flow_do_not_prove_safety(self):
        sources = [ACCESS.replace('contract Vault {', 'contract Vault is Base {'),
                   ACCESS.replace('balance = 1;', 'if (balance == 0) { balance = 1; }'),
                   ACCESS.replace('balance = 1;', 'uint storage aliasValue = balance; aliasValue = 1; balance = 1;'),
                   ACCESS.replace('balance = 1;', 'helper(); balance = 1;')]
        for source in sources:
            with self.subTest(source=source):
                result = self.assess(source)
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertNotEqual('SUPPORTED', result['protectionVerdict'])

    def test_unknown_visibility_and_internal_entry_are_conservative(self):
        for visibility in ['', 'internal', 'private']:
            with self.subTest(visibility=visibility):
                result = self.assess(ACCESS.replace('public', visibility))
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertEqual('UNKNOWN', self.obligations(result)['entry_coverage']['status'])

    def test_late_guard_is_not_a_pre_risk_guard_or_a_proven_exploit(self):
        source = ACCESS.replace('require(msg.sender == owner);\n    balance = 1;',
                                'balance = 1;\n    require(msg.sender == owner);')
        result = self.assess(source)
        self.assertEqual('REFUTED', self.obligations(result)['pre_risk_guard']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertNotEqual('REACHABLE', result['pathEvidence']['status'])

    def test_modifier_order_overrides_source_line_order(self):
        prefix = 'contract Vault { address owner; uint balance; modifier guard() {'
        for body, status in [('require(msg.sender == owner); _;', 'SUPPORTED'),
                             ('_; require(msg.sender == owner);', 'REFUTED')]:
            with self.subTest(body=body):
                source = prefix + body + '} function withdraw() public guard { balance = 1; } }'
                result = self.assess(source)
                self.assertEqual(status, self.obligations(result)['pre_risk_guard']['status'])

    def test_wrong_actor_and_other_function_guard_do_not_cover_target(self):
        for source in [ACCESS.replace('msg.sender == owner', 'tx.origin == owner'),
                       ACCESS.replace('    require(msg.sender == owner);', '').replace(
                           '  function withdraw()', '  function other() public { require(msg.sender == owner); }\n  function withdraw()')]:
            with self.subTest(source=source):
                result = self.assess(source)
                self.assertEqual('REFUTED', self.obligations(result)['actor']['status'])
                self.assertEqual('UNKNOWN', result['verdict'])

    def test_authority_mutation_invalidates_state_version(self):
        source = ACCESS.replace('    balance = 1;', '    owner = msg.sender;\n    balance = 1;')
        hypothesis, facts = self.case(source)
        hypothesis['riskLine'] = 7
        result = evaluate(hypothesis, facts, self.tools(hypothesis, facts), source=source)
        self.assertEqual('REFUTED', self.obligations(result)['state_version']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_uncovered_public_entry_prevents_protection_verdict(self):
        source = ACCESS.replace('\n}', '\n  function bypass() public { balance = 2; }\n}')
        result = self.assess(source)
        self.assertEqual('REFUTED', self.obligations(result)['entry_coverage']['status'])
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_takeover_with_scoped_corroboration_supports_vulnerability(self):
        result = self.assess(TAKEOVER)
        self.assertEqual(('SUPPORTED', 'REFUTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual('REACHABLE', result['pathEvidence']['status'])
        self.assertTrue(any('engine' in ref for ref in result['references']))

    def test_wrong_category_function_contract_file_or_tool_hash_cannot_corroborate(self):
        hypothesis, facts = self.case(TAKEOVER)
        baseline = self.tools(hypothesis, facts)
        variants = []
        wrong_type = copy.deepcopy(baseline)
        wrong_type[0]['issues'][0]['check'] = 'reentrancy-eth'
        variants.append(wrong_type)
        for field, value in [('name', 'other'), ('source_mapping', {'lines': [hypothesis['riskLine']], 'filename_relative': 'other/Vault.sol'}),
                             ('type_specific_fields', {'parent': {'type': 'contract', 'name': 'Other'}})]:
            altered = copy.deepcopy(baseline)
            altered[0]['issues'][0]['elements'][0][field] = value
            variants.append(altered)
        altered = copy.deepcopy(baseline)
        altered[0]['sourceHash'] = '0' * 64
        variants.append(altered)
        variants.append([{'engine': 'SLITHER', 'status': 'OK', 'issues': [
            {'check': 'protected-vars', 'elements': [{'source_mapping': {'lines': [hypothesis['riskLine']]}}]}]}])
        for tools in variants:
            with self.subTest(tools=tools):
                result = evaluate(hypothesis, facts, tools, source=TAKEOVER)
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertFalse(any('engine' in ref for ref in result['references']))

    def test_tool_failure_is_not_a_verifier_failure_counter(self):
        hypothesis, facts = self.case(TAKEOVER)
        tools = self.tools(hypothesis, facts) + [{'engine': 'MYTHRIL', 'status': 'FAILED', 'issues': []}]
        result = evaluate(hypothesis, facts, tools, source=TAKEOVER)
        self.assertEqual('UNKNOWN', result['verdict'])
        self.assertNotIn('failed', result)
        self.assertNotIn('denominators', result)

    def test_java_contract_file_and_hash_bind_corroboration(self):
        hypothesis, facts = self.case(TAKEOVER)
        tools = self.tools(hypothesis, facts)
        tools[0]['sourceFile'] = 'Contract.sol'
        mapping = tools[0]['issues'][0]['elements'][0]['source_mapping']
        mapping.update(filename_relative='Contract.sol', filename_absolute='/tmp/audit-test/Contract.sol')
        result = evaluate(hypothesis, facts, tools, source=TAKEOVER)
        self.assertEqual('SUPPORTED', result['verdict'])
        for field, value in [('filename_relative', 'Other.sol'), ('filename_absolute', '/tmp/audit-test/Other.sol')]:
            changed = copy.deepcopy(tools)
            changed[0]['issues'][0]['elements'][0]['source_mapping'][field] = value
            self.assertEqual('UNKNOWN', evaluate(hypothesis, facts, changed, source=TAKEOVER)['verdict'])
        for missing in ['sourceHash', 'sourceFile']:
            changed = copy.deepcopy(tools)
            changed[0].pop(missing)
            self.assertEqual('UNKNOWN', evaluate(hypothesis, facts, changed, source=TAKEOVER)['verdict'])

    def test_malformed_alert_category_is_unknown_instead_of_raising(self):
        hypothesis, facts = self.case(TAKEOVER)
        tools = self.tools(hypothesis, facts)
        tools[0]['issues'][0]['check'] = ['protected-vars']
        result = evaluate(hypothesis, facts, tools, source=TAKEOVER)
        self.assertEqual('UNKNOWN', result['verdict'])

    def test_malformed_tool_details_do_not_make_protected_source_safe(self):
        hypothesis, facts = self.case()
        for issues in [[None], [{'check': ['protected-vars']}]]:
            with self.subTest(issues=issues):
                tools = [{'engine': 'SLITHER', 'status': 'OK', 'sourceHash': facts['sourceHash'], 'issues': issues}]
                self.assertEqual('UNKNOWN', evaluate(hypothesis, facts, tools, source=ACCESS)['verdict'])

    def test_cei_before_call_proves_state_order_and_blocked_repeat(self):
        source = reentrancy_source(before=True)
        result = self.assess(source, 'REENTRANCY', 'CALL')
        self.assertEqual('SUPPORTED', self.obligations(result)['state_version']['status'])
        self.assertEqual('SUPPORTED', self.obligations(result)['bypass']['status'])
        # 存款入口可重新写入余额；完整直线语法不证明跨入口经济语义。
        self.assertEqual(('UNKNOWN', 'UNKNOWN'), (result['verdict'], result['protectionVerdict']))

    def test_cei_with_no_other_resource_entry_has_all_six_obligations(self):
        source = reentrancy_source(before=True).replace(
            '  function deposit() public payable { balances[msg.sender] = 1; }\n', '')
        result = self.assess(source, 'REENTRANCY', 'CALL')
        self.assertEqual(('REFUTED', 'SUPPORTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual({'SUPPORTED'}, {item['status'] for item in result['obligations']})

    def test_cei_after_call_needs_program_path_and_matching_alert(self):
        source = reentrancy_source()
        hypothesis, facts = self.case(source, 'REENTRANCY', 'CALL')
        tools = self.tools(hypothesis, facts, 'reentrancy-eth')
        result = evaluate(hypothesis, facts, tools, source=source)
        self.assertEqual('REFUTED', self.obligations(result)['state_version']['status'])
        self.assertEqual('REFUTED', self.obligations(result)['bypass']['status'])
        self.assertEqual(('SUPPORTED', 'REFUTED'), (result['verdict'], result['protectionVerdict']))
        self.assertEqual('REACHABLE', result['pathEvidence']['status'])
        without_tool = evaluate(hypothesis, facts, [], source=source)
        self.assertEqual('UNKNOWN', without_tool['verdict'])
        self.assertEqual('REFUTED', self.obligations(without_tool)['state_version']['status'])

    def test_wrong_resource_or_increment_is_not_cei_protection(self):
        for write in ['balances[other] = 0;', 'balances[msg.sender] += 1;', 'balances[msg.sender] = 1;']:
            with self.subTest(write=write):
                source = reentrancy_source(True, write).replace('withdraw()', 'withdraw(address other)')
                result = self.assess(source, 'REENTRANCY', 'CALL')
                self.assertEqual('UNKNOWN', result['verdict'])
                self.assertNotEqual('SUPPORTED', self.obligations(result)['state_version']['status'])

    def test_guard_alone_and_unreachable_positive_balance_are_not_proofs(self):
        for source in [reentrancy_source().replace('    balances[msg.sender] = 0;', ''),
                       reentrancy_source().replace('  function deposit() public payable { balances[msg.sender] = 1; }\n', '')]:
            with self.subTest(source=source):
                hypothesis, facts = self.case(source, 'REENTRANCY', 'CALL')
                result = evaluate(hypothesis, facts, self.tools(hypothesis, facts, 'reentrancy-eth'), source=source)
                self.assertEqual('UNKNOWN', result['verdict'])

    def test_references_are_resolvable_and_inputs_are_preserved(self):
        hypothesis, facts = self.case()
        tools = self.tools(hypothesis, facts)
        original = copy.deepcopy((hypothesis, facts, tools))
        result = evaluate(hypothesis, facts, tools, source=ACCESS)
        known = {fact['id']: fact for fact in facts['facts']}
        for item in result['obligations']:
            self.assertTrue(item['reason'])
            self.assertTrue(item['references'])
            for ref in item['references']:
                if 'factId' in ref:
                    fact = known[ref['factId']]
                    self.assertEqual((fact['line'], fact['scope']), (ref['line'], ref['scope']))
                else:
                    tool = next(tool for tool in tools if tool['engine'] == ref['engine'])
                    self.assertEqual('protected-vars', tool['issues'][ref['issueIndex']]['check'])
        self.assertEqual(original, (hypothesis, facts, tools))

    def test_invalid_inputs_raise_value_error(self):
        for hypothesis, facts, tools in [(None, {}, []), ({'riskLine': True}, {}, []),
                                          ({'riskLine': 0}, {}, []), ({'riskLine': 1}, [], []),
                                          ({'riskLine': 1}, {}, None)]:
            with self.subTest(hypothesis=hypothesis):
                with self.assertRaises(ValueError):
                    evaluate(hypothesis, facts, tools)


if __name__ == '__main__':
    unittest.main()
