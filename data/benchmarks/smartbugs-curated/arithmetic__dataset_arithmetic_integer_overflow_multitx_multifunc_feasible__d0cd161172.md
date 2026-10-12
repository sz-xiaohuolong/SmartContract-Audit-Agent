---
Dataset: smartbugs-curated
Name: integer_overflow_multitx_multifunc_feasible.sol
Category: arithmetic
Pragma: 0.4.23
Origin-Path: dataset/arithmetic/integer_overflow_multitx_multifunc_feasible.sol
Source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
Vulnerable-Lines: 25
---

# Vulnerability Reference Case: arithmetic

## Source Code
```solidity
/*
 * @source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
 * @author: Suhabe Bugrara
 * @vulnerable_at_lines: 25
 */

//Multi-transactional, multi-function
//Arithmetic instruction reachable

pragma solidity ^0.4.23;

contract IntegerOverflowMultiTxMultiFuncFeasible {
    uint256 private initialized = 0;
    uint256 public count = 1;

    function init() public {
        initialized = 1;
    }

    function run(uint256 input) {
        if (initialized == 0) {
            return;
        }
        // <yes> <report> ARITHMETIC
        count -= input;
    }
}
```
