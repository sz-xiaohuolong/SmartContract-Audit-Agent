---
Dataset: smartbugs-curated
Name: FindThisHash.sol
Category: front_running
Pragma: 0.4.22
Origin-Path: dataset/front_running/FindThisHash.sol
Source: https://github.com/sigp/solidity-security-blog
Vulnerable-Lines: 17
---

# Vulnerability Reference Case: front_running

## Source Code
```solidity
/*
 * @source: https://github.com/sigp/solidity-security-blog
 * @author: -
 * @vulnerable_at_lines: 17
 */

pragma solidity ^0.4.22;

contract FindThisHash {
    bytes32 constant public hash = 0xb5b5b97fafd9855eec9b41f74dfb6c38f5951141f9a3ecd7f44d5479b630ee0a;

    constructor() public payable {} // load with ether

    function solve(string solution) public {
        // If you can find the pre image of the hash, receive 1000 ether
         // <yes> <report> FRONT_RUNNING
        require(hash == sha3(solution));
        msg.sender.transfer(1000 ether);
    }
}
```
