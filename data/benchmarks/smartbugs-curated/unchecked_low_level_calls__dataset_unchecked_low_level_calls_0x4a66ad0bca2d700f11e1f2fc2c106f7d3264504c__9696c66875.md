---
Dataset: smartbugs-curated
Name: 0x4a66ad0bca2d700f11e1f2fc2c106f7d3264504c.sol
Category: unchecked_low_level_calls
Pragma: 0.4.18
Origin-Path: dataset/unchecked_low_level_calls/0x4a66ad0bca2d700f11e1f2fc2c106f7d3264504c.sol
Source: etherscan.io
Vulnerable-Lines: 19
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 19 
 */

pragma solidity ^0.4.18;

contract EBU{
    address public from = 0x9797055B68C5DadDE6b3c7d5D80C9CFE2eecE6c9;
    address public caddress = 0x1f844685f7Bf86eFcc0e74D8642c54A257111923;
    
    function transfer(address[] _tos,uint[] v)public returns (bool){
        require(msg.sender == 0x9797055B68C5DadDE6b3c7d5D80C9CFE2eecE6c9);
        require(_tos.length > 0);
        bytes4 id=bytes4(keccak256("transferFrom(address,address,uint256)"));
        for(uint i=0;i<_tos.length;i++){
            // <yes> <report> UNCHECKED_LL_CALLS
            caddress.call(id,from,_tos[i],v[i]*1000000000000000000);
        }
        return true;
    }
}
```
