---
Dataset: smartbugs-curated
Name: 0x610495793564aed0f9c7fc48dc4c7c9151d34fd6.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0x610495793564aed0f9c7fc48dc4c7c9151d34fd6.sol
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
    
    function sendMoney(address _target, uint _value, bytes _data) public onlyOwner {
        // <yes> <report> UNCHECKED_LL_CALLS
        _target.call.value(_value)(_data);
    }
}
```
