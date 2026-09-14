---
Dataset: smartbugs-curated
Name: reentrancy_dao.sol
Category: reentrancy
Pragma: 0.4.19
Origin-Path: dataset/reentrancy/reentrancy_dao.sol
Source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
Vulnerable-Lines: 18
---

# Vulnerability Reference Case: reentrancy

## Source Code
```solidity
/*
 * @source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
 * @author: Suhabe Bugrara
 * @vulnerable_at_lines: 18
 */

pragma solidity ^0.4.19;

contract ReentrancyDAO {
    mapping (address => uint) credit;
    uint balance;

    function withdrawAll() public {
        uint oCredit = credit[msg.sender];
        if (oCredit > 0) {
            balance -= oCredit;
            // <yes> <report> REENTRANCY
            bool callResult = msg.sender.call.value(oCredit)();
            require (callResult);
            credit[msg.sender] = 0;
        }
    }

    function deposit() public payable {
        credit[msg.sender] += msg.value;
        balance += msg.value;
    }
}
```
