---
Dataset: smartbugs-curated
Name: 0x52d2e0f9b01101a59b38a3d05c80b7618aeed984.sol
Category: unchecked_low_level_calls
Pragma: 0.4.19
Origin-Path: dataset/unchecked_low_level_calls/0x52d2e0f9b01101a59b38a3d05c80b7618aeed984.sol
Source: etherscan.io
Vulnerable-Lines: 27
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 27
 */

pragma solidity ^0.4.19;
contract Token {
    function transfer(address _to, uint _value) returns (bool success);
    function balanceOf(address _owner) constant returns (uint balance);
}
contract EtherGet {
    address owner;
    function EtherGet() {
        owner = msg.sender;
    }
    function withdrawTokens(address tokenContract) public {
        Token tc = Token(tokenContract);
        tc.transfer(owner, tc.balanceOf(this));
    }
    function withdrawEther() public {
        owner.transfer(this.balance);
    }
    function getTokens(uint num, address addr) public {
        for(uint i = 0; i < num; i++){
            // <yes> <report> UNCHECKED_LL_CALLS
            addr.call.value(0 wei)();
        }
    }
}
```
