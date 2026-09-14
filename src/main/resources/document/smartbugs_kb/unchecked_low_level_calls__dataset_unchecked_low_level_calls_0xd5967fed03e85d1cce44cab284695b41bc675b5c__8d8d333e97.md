---
Dataset: smartbugs-curated
Name: 0xd5967fed03e85d1cce44cab284695b41bc675b5c.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0xd5967fed03e85d1cce44cab284695b41bc675b5c.sol
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
 
contract demo{
    
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
