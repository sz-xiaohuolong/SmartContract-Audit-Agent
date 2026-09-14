---
Dataset: smartbugs-curated
Name: roulette.sol
Category: time_manipulation
Pragma: 0.4.25
Origin-Path: dataset/time_manipulation/roulette.sol
Source: https://github.com/sigp/solidity-security-blog
Vulnerable-Lines: 18, 20
---

# Vulnerability Reference Case: time_manipulation

## Source Code
```solidity
/*
 * @source: https://github.com/sigp/solidity-security-blog
 * @author: -
 * @vulnerable_at_lines: 18,20
 */

pragma solidity ^0.4.25;

contract Roulette {
    uint public pastBlockTime; // Forces one bet per block

    constructor() public payable {} // initially fund contract

    // fallback function used to make a bet
    function () public payable {
        require(msg.value == 10 ether); // must send 10 ether to play
        // <yes> <report> TIME_MANIPULATION
        require(now != pastBlockTime); // only 1 transaction per block
        // <yes> <report> TIME_MANIPULATION
        pastBlockTime = now;
        if(now % 15 == 0) { // winner
            msg.sender.transfer(this.balance);
        }
    }
}
```
