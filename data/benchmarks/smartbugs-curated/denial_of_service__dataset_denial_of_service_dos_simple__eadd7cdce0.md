---
Dataset: smartbugs-curated
Name: dos_simple.sol
Category: denial_of_service
Pragma: 0.4.25
Origin-Path: dataset/denial_of_service/dos_simple.sol
Source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/dos_gas_limit/dos_simple.sol
Vulnerable-Lines: 17, 18
---

# Vulnerability Reference Case: denial_of_service

## Source Code
```solidity
/*
 * @source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/dos_gas_limit/dos_simple.sol
 * @author: -
 * @vulnerable_at_lines: 17,18
 */


pragma solidity ^0.4.25;

contract DosOneFunc {

    address[] listAddresses;

    function ifillArray() public returns (bool){
        if(listAddresses.length<1500) {
            // <yes> <report> DENIAL_OF_SERVICE
            for(uint i=0;i<350;i++) {
                listAddresses.push(msg.sender);
            }
            return true;

        } else {
            listAddresses = new address[](0);
            return false;
        }
    }
}
```
