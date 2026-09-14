---
Dataset: smartbugs-curated
Name: integer_overflow_minimal.sol
Category: arithmetic
Pragma: 0.4.19
Origin-Path: dataset/arithmetic/integer_overflow_minimal.sol
Source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/integer_overflow_and_underflow/integer_overflow_minimal.sol
Vulnerable-Lines: 17
---

# Vulnerability Reference Case: arithmetic

## Source Code
```solidity
/*
 * @source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/integer_overflow_and_underflow/integer_overflow_minimal.sol
 * @author: -
 * @vulnerable_at_lines: 17
 */

//Single transaction overflow
//Post-transaction effect: overflow escapes to publicly-readable storage

pragma solidity ^0.4.19;

contract IntegerOverflowMinimal {
    uint public count = 1;

    function run(uint256 input) public {
        // <yes> <report> ARITHMETIC
        count -= input;
    }
}
```
