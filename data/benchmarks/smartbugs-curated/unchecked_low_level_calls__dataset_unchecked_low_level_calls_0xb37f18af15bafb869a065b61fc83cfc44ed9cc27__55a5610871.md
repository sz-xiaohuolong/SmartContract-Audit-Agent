---
Dataset: smartbugs-curated
Name: 0xb37f18af15bafb869a065b61fc83cfc44ed9cc27.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0xb37f18af15bafb869a065b61fc83cfc44ed9cc27.sol
Source: etherscan.io
Vulnerable-Lines: 33
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 33
 */

pragma solidity ^0.4.24;


contract SimpleWallet {
    address public owner = msg.sender;
    uint public depositsCount;
    
    modifier onlyOwner {
        require(msg.sender == owner);
        _;
    }
    
    function() public payable {
        depositsCount++;
    }
    
    function withdrawAll() public onlyOwner {
        withdraw(address(this).balance);
    }
    
    function withdraw(uint _value) public onlyOwner {
        msg.sender.transfer(_value);
    }
    
    function sendMoney(address _target, uint _value) public onlyOwner {
        // <yes> <report> UNCHECKED_LL_CALLS
        _target.call.value(_value)();
    }
}
```
