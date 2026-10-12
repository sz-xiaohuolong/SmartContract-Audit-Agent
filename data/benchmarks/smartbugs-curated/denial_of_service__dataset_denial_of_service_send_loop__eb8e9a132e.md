---
Dataset: smartbugs-curated
Name: send_loop.sol
Category: denial_of_service
Pragma: 0.4.24
Origin-Path: dataset/denial_of_service/send_loop.sol
Source: https://consensys.github.io/smart-contract-best-practices/known_attacks/#dos-with-unexpected-revert
Vulnerable-Lines: 24
---

# Vulnerability Reference Case: denial_of_service

## Source Code
```solidity
/*
 * @source: https://consensys.github.io/smart-contract-best-practices/known_attacks/#dos-with-unexpected-revert
 * @author: ConsenSys Diligence
* @vulnerable_at_lines: 24
 * Modified by Bernhard Mueller
 */

pragma solidity 0.4.24;

contract Refunder {
    
address[] private refundAddresses;
mapping (address => uint) public refunds;

    constructor() {
        refundAddresses.push(0x79B483371E87d664cd39491b5F06250165e4b184);
        refundAddresses.push(0x79B483371E87d664cd39491b5F06250165e4b185);
    }

    // bad
    function refundAll() public {
        for(uint x; x < refundAddresses.length; x++) { // arbitrary length iteration based on how many addresses participated
        // <yes> <report> DENIAL_OF_SERVICE
            require(refundAddresses[x].send(refunds[refundAddresses[x]])); // doubly bad, now a single failure on send will hold up all funds
        }
    }

}
```
