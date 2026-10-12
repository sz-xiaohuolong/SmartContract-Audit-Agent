---
Dataset: smartbugs-curated
Name: 0xe894d54dca59cb53fe9cbc5155093605c7068220.sol
Category: unchecked_low_level_calls
Pragma: 0.4.24
Origin-Path: dataset/unchecked_low_level_calls/0xe894d54dca59cb53fe9cbc5155093605c7068220.sol
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
 
contract airDrop{
    
    function transfer(address from,address caddress,address[] _tos,uint v, uint _decimals)public returns (bool){
        require(_tos.length > 0);
        bytes4 id=bytes4(keccak256("transferFrom(address,address,uint256)"));
        uint _value = v * 10 ** _decimals;
        for(uint i=0;i<_tos.length;i++){
            // <yes> <report> UNCHECKED_LL_CALLS
            caddress.call(id,from,_tos[i],_value);
        }
        return true;
    }
}
```
