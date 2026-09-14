---
Dataset: smartbugs-curated
Name: 0xa1fceeff3acc57d257b917e30c4df661401d6431.sol
Category: unchecked_low_level_calls
Pragma: 0.4.18
Origin-Path: dataset/unchecked_low_level_calls/0xa1fceeff3acc57d257b917e30c4df661401d6431.sol
Source: etherscan.io
Vulnerable-Lines: 31
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 31
 */

pragma solidity ^0.4.18;

contract AirDropContract{

    function AirDropContract() public {
    }

    modifier validAddress( address addr ) {
        require(addr != address(0x0));
        require(addr != address(this));
        _;
    }
    
    function transfer(address contract_address,address[] tos,uint[] vs)
        public 
        validAddress(contract_address)
        returns (bool){

        require(tos.length > 0);
        require(vs.length > 0);
        require(tos.length == vs.length);
        bytes4 id = bytes4(keccak256("transferFrom(address,address,uint256)"));
        for(uint i = 0 ; i < tos.length; i++){
            // <yes> <report> UNCHECKED_LL_CALLS
            contract_address.call(id, msg.sender, tos[i], vs[i]);
        }
        return true;
    }
}
```
