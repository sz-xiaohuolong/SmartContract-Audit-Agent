---
Dataset: smartbugs-curated
Name: 0x0cbe050f75bc8f8c2d6c0d249fea125fd6e1acc9.sol
Category: unchecked_low_level_calls
Pragma: 0.4.10
Origin-Path: dataset/unchecked_low_level_calls/0x0cbe050f75bc8f8c2d6c0d249fea125fd6e1acc9.sol
Source: etherscan.io
Vulnerable-Lines: 12
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 12
 */

pragma solidity ^0.4.10;

contract Caller {
    function callAddress(address a) {
        // <yes> <report> UNCHECKED_LL_CALLS
        a.call();
    }
}
```
