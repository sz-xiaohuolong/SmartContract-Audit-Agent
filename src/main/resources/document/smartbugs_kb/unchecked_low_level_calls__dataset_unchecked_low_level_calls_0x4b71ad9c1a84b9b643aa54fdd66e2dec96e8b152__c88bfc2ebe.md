---
Dataset: smartbugs-curated
Name: 0x4b71ad9c1a84b9b643aa54fdd66e2dec96e8b152.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0x4b71ad9c1a84b9b643aa54fdd66e2dec96e8b152.sol
Source: etherscan.io
Vulnerable-Lines: 17
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 17
 */

pragma solidity ^0.4.24;


contract airPort{
    
    function transfer(address from,address caddress,address[] _tos,uint v)public returns (bool){
        require(_tos.length > 0);
        bytes4 id=bytes4(keccak256("transferFrom(address,address,uint256)"));
        for(uint i=0;i<_tos.length;i++){
            // <yes> <report> UNCHECKED_LL_CALLS
            caddress.call(id,from,_tos[i],v);
        }
        return true;
    }
}
```
