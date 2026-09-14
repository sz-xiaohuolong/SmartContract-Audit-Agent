---
Dataset: smartbugs-curated
Name: 0x4051334adc52057aca763453820cb0e045076ef3.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0x4051334adc52057aca763453820cb0e045076ef3.sol
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
 
contract airdrop{
    
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
