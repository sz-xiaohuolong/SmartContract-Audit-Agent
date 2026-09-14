---
Dataset: smartbugs-curated
Name: 0xb7c5c5aa4d42967efe906e1b66cb8df9cebf04f7.sol
Category: unchecked_low_level_calls
Pragma: 0.4.23
Origin-Path: dataset/unchecked_low_level_calls/0xb7c5c5aa4d42967efe906e1b66cb8df9cebf04f7.sol
Source: etherscan.io
Vulnerable-Lines: 25
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 25
 */

pragma solidity ^0.4.23;

/*
!!! THIS CONTRACT IS EXPLOITABLE AND FOR EDUCATIONAL PURPOSES ONLY !!!

This smart contract allows a user to (insecurely) store funds
in this smart contract and withdraw them at any later point in time
*/

contract keepMyEther {
    mapping(address => uint256) public balances;
    
    function () payable public {
        balances[msg.sender] += msg.value;
    }
    
    function withdraw() public {
        // <yes> <report> UNCHECKED_LL_CALLS
        msg.sender.call.value(balances[msg.sender])();
        balances[msg.sender] = 0;
    }
}
```
