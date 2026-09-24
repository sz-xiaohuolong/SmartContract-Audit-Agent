"""受限事实提取的作用域、时序与降级语义。"""
import unittest
from program_facts import extract_facts


class ProgramFactsTest(unittest.TestCase):
    def facts(self, body, modifier=""):
        return extract_facts('contract C { address owner; uint balance; ' + modifier +
                             ' function withdraw() public ' + ('guard ' if modifier else '') + '{' + body + '} }')

    def test_extracts_state_caller_checks_and_call_write_order(self):
        result = self.facts('require(msg.sender == owner); msg.sender.call{value: 1}(""); balance = 0;')
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(["owner", "balance"], [v["name"] for v in result["stateVariables"]])
        self.assertEqual(["CHECK", "CALL", "WRITE"], [f["kind"] for f in result["facts"]])
        check, call, write = result["facts"]
        self.assertEqual(("msg.sender", "owner"), (check["subject"], check["resource"]))
        self.assertEqual("balance", write["resource"])
        self.assertLess(call["order"], write["order"])

    def test_modifiers_expand_in_execution_order_not_source_order(self):
        result = self.facts('balance = 1;', 'modifier guard() { require(msg.sender == owner); _; }')
        self.assertEqual(["CHECK", "WRITE"], [f["kind"] for f in result["facts"]])
        self.assertEqual(["guard"], result["scopes"][0]["modifiers"])
        late = self.facts('balance = 1;', 'modifier guard() { _; require(msg.sender == owner); }')
        self.assertEqual(["WRITE", "CHECK"], [f["kind"] for f in late["facts"]])

    def test_wrong_subject_late_check_and_wrong_resource_remain_distinct(self):
        result = self.facts('balance = 1; require(tx.origin == owner);')
        self.assertEqual(["WRITE", "CHECK"], [f["kind"] for f in result["facts"]])
        self.assertEqual("tx.origin", result["facts"][1]["subject"])
        data = extract_facts('contract C { mapping(address => uint) balances; function f(address other) public { balances[other] = 0; msg.sender.call(""); } }')
        self.assertEqual("balances[other]", data["facts"][0]["resource"])
        self.assertEqual("COMPLETE", data["status"])

    def test_branch_bypass_unresolved_modifier_and_internal_call_are_unknown(self):
        for body, modifier in [('if (ok) { require(msg.sender == owner); } balance = 0;', ''),
                               ('helper(); balance = 0;', ''), ('balance = 0;', 'modifier guard() { if (ok) { _; } }')]:
            result = self.facts(body, modifier)
            self.assertEqual("PARTIAL", result["status"])
            self.assertFalse(result["scopes"][0]["complete"])
        result = extract_facts('contract C { uint x; function f() public onlyOwner { x = 1; } }')
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual([], [f for f in result["facts"] if f["kind"] == "CHECK"])

    def test_comments_strings_and_other_function_do_not_protect_target(self):
        source = '''contract C { uint balance; address owner;
        function other() public { require(msg.sender == owner); }
        function f() public { /* require(msg.sender == owner); */
          string memory note = "require(msg.sender == owner);";
          balance = 0;
        }}'''
        result = extract_facts(source)
        target = next(s for s in result["scopes"] if s["name"] == "f")
        self.assertEqual(["WRITE"], [f["kind"] for f in result["facts"] if f["scope"] == target["id"]])
        self.assertEqual(5, next(f for f in result["facts"] if f["kind"] == "WRITE")["line"])

    def test_malformed_or_unsupported_source_never_becomes_complete_empty(self):
        for source in ['contract C {', 'not solidity', 'contract C { /* unfinished']:
            self.assertEqual("FAILED", extract_facts(source)["status"])
        for source in ['contract C is Base { uint x; function f() public { x = 1; } }',
                       'contract C { uint x; function f() public { assembly { sstore(0, 1) } } }']:
            with self.subTest(source=source):
                self.assertEqual("PARTIAL", extract_facts(source)["status"])

    def test_rhs_call_shadowed_state_and_member_alias_are_not_definite(self):
        for body in ['balance = msg.sender.send(1);', 'address payable owner = msg.sender; require(msg.sender == owner); balance = 0;',
                     'obj.balance = 0; msg.sender.call("");']:
            self.assertEqual("PARTIAL", self.facts(body)["status"])

    def test_overloads_on_same_line_have_distinct_scopes_and_fact_ids(self):
        data = extract_facts('contract C { uint x; function f() public { x = 1; } function f(uint a) public { x = a; } }')
        self.assertEqual(2, len({s["id"] for s in data["scopes"]}))
        self.assertEqual(2, len({f["id"] for f in data["facts"]}))

    def test_alias_tuple_and_unrecognized_writes_do_not_imply_absence(self):
        for body in ['uint storage aliasValue = balances[msg.sender]; aliasValue = 0; msg.sender.call("");',
                     '(balance, owner) = (0, msg.sender); msg.sender.call("");']:
            self.assertEqual("PARTIAL", self.facts(body)["status"])
        for body in ['++balance; msg.sender.call("");', 'balance *= 2; msg.sender.call("");']:
            result = self.facts(body)
            self.assertTrue(result["status"] == "PARTIAL" or result["facts"][0]["kind"] == "WRITE")

    def test_short_circuit_and_nested_mapping_cannot_prove_write_presence_or_absence(self):
        for body in ['bool ok = flag && ((balance = 0) == 0); msg.sender.call("");',
                     'bool ok = flag || ((balance = 0) == 0); msg.sender.call("");',
                     'balances[msg.sender][a] = 0; msg.sender.call("");']:
            source = 'contract C { bool flag; uint balance; mapping(address => mapping(uint => uint)) balances; function f(uint a) public {' + body + '} }'
            with self.subTest(body=body):
                self.assertEqual("PARTIAL", extract_facts(source)["status"])

    def test_mutated_index_and_nested_assignment_keep_data_flow_unknown(self):
        for body in ['balances[a] = 0; a = b; msg.sender.call("");',
                     'require(msg.sender == owners[a]); a = b; balance = 1;',
                     'balances[index] = 0; index = 1; msg.sender.call("");',
                     'balance = index = 1; msg.sender.call("");',
                     'balances[a] = 0; ++a; msg.sender.call("");']:
            with self.subTest(body=body):
                source = 'contract C { uint balance; uint index; mapping(uint => uint) balances; mapping(uint => address) owners; function f(uint a, uint b) public {' + body + '} }'
                self.assertEqual("PARTIAL", extract_facts(source)["status"])
