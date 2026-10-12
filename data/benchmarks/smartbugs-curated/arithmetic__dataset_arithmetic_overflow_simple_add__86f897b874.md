---
Dataset: smartbugs-curated
Name: overflow_simple_add.sol
Category: arithmetic
Pragma: 0.4.25
Origin-Path: dataset/arithmetic/overflow_simple_add.sol
Source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-101#overflow-simple-addsol
Vulnerable-Lines: 14
---

# Vulnerability Reference Case: arithmetic

## Source Code
```solidity
/*
 * @source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-101#overflow-simple-addsol
 * @author: -
 * @vulnerable_at_lines: 14
 */

pragma solidity 0.4.25;

contract Overflow_Add {
    uint public balance = 1;

    function add(uint256 deposit) public {
        // <yes> <report> ARITHMETIC
        balance += deposit;
    }
}
```
