---
Dataset: smartbugs-curated
Name: 0xf29ebe930a539a60279ace72c707cba851a57707.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0xf29ebe930a539a60279ace72c707cba851a57707.sol
Source: etherscan.io
Vulnerable-Lines: 16
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 16
 */

pragma solidity ^0.4.24;


contract B {
    address public owner = msg.sender;
    
    function go() public payable {
        address target = 0xC8A60C51967F4022BF9424C337e9c6F0bD220E1C;
        // <yes> <report> UNCHECKED_LL_CALLS
        target.call.value(msg.value)();
        owner.transfer(address(this).balance);
    }
    
    function() public payable {
    }
}
```
