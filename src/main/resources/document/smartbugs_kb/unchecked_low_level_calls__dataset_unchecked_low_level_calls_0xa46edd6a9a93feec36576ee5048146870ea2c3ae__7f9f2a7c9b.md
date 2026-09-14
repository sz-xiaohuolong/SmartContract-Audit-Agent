---
Dataset: smartbugs-curated
Name: 0xa46edd6a9a93feec36576ee5048146870ea2c3ae.sol
Category: unchecked_low_level_calls
Pragma: 0.4.18
Origin-Path: dataset/unchecked_low_level_calls/0xa46edd6a9a93feec36576ee5048146870ea2c3ae.sol
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

pragma solidity ^0.4.18;

contract EBU{
    
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
