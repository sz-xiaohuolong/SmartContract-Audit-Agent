---
Dataset: smartbugs-curated
Name: reentrancy_insecure.sol
Category: reentrancy
Pragma: 0.5.0
Origin-Path: dataset/reentrancy/reentrancy_insecure.sol
Source: https://consensys.github.io/smart-contract-best-practices/known_attacks/
Vulnerable-Lines: 17
---

# Vulnerability Reference Case: reentrancy

## Source Code
```solidity
/*
 * @source: https://consensys.github.io/smart-contract-best-practices/known_attacks/
 * @author: consensys
 * @vulnerable_at_lines: 17
 */

pragma solidity ^0.5.0;

contract Reentrancy_insecure {

    // INSECURE
    mapping (address => uint) private userBalances;

    function withdrawBalance() public {
        uint amountToWithdraw = userBalances[msg.sender];
        // <yes> <report> REENTRANCY
        (bool success, ) = msg.sender.call.value(amountToWithdraw)(""); // At this point, the caller's code is executed, and can call withdrawBalance again
        require(success);
        userBalances[msg.sender] = 0;
    }
}
```
