---
Dataset: smartbugs-curated
Name: simple_dao.sol
Category: reentrancy
Pragma: 0.4.2
Origin-Path: dataset/reentrancy/simple_dao.sol
Source: http://blockchain.unica.it/projects/ethereum-survey/attacks.html#simpledao
Vulnerable-Lines: 19
---

# Vulnerability Reference Case: reentrancy

## Source Code
```solidity
/*
 * @source: http://blockchain.unica.it/projects/ethereum-survey/attacks.html#simpledao
 * @author: -
 * @vulnerable_at_lines: 19
 */

pragma solidity ^0.4.2;

contract SimpleDAO {
  mapping (address => uint) public credit;

  function donate(address to) payable {
    credit[to] += msg.value;
  }

  function withdraw(uint amount) {
    if (credit[msg.sender]>= amount) {
      // <yes> <report> REENTRANCY
      bool res = msg.sender.call.value(amount)();
      credit[msg.sender]-=amount;
    }
  }

  function queryCredit(address to) returns (uint){
    return credit[to];
  }
}
```
