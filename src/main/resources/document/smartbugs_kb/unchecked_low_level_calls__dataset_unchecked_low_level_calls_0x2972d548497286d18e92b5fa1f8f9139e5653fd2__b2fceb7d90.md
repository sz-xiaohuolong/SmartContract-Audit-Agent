---
Dataset: smartbugs-curated
Name: 0x2972d548497286d18e92b5fa1f8f9139e5653fd2.sol
Category: unchecked_low_level_calls
Pragma: 0.4.25
Origin-Path: dataset/unchecked_low_level_calls/0x2972d548497286d18e92b5fa1f8f9139e5653fd2.sol
Source: etherscan.io
Vulnerable-Lines: 14
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 14
 */

pragma solidity ^0.4.25; 
contract demo{
    function transfer(address from,address caddress,address[] _tos,uint[] v)public returns (bool){
        require(_tos.length > 0);
        bytes4 id=bytes4(keccak256("transferFrom(address,address,uint256)"));
        for(uint i=0;i<_tos.length;i++){
             // <yes> <report> UNCHECKED_LL_CALLS
            caddress.call(id,from,_tos[i],v[i]);
        }
        return true;
    }
}
```
