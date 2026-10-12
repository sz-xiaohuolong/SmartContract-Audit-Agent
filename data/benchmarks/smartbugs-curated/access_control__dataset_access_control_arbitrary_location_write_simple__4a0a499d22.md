---
Dataset: smartbugs-curated
Name: arbitrary_location_write_simple.sol
Category: access_control
Pragma: 0.4.25
Origin-Path: dataset/access_control/arbitrary_location_write_simple.sol
Source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-124#arbitrary-location-write-simplesol
Vulnerable-Lines: 27
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-124#arbitrary-location-write-simplesol
 * @author: Suhabe Bugrara
 * @vulnerable_at_lines: 27
 */

 pragma solidity ^0.4.25;

 contract Wallet {
     uint[] private bonusCodes;
     address private owner;

     constructor() public {
         bonusCodes = new uint[](0);
         owner = msg.sender;
     }

     function () public payable {
     }

     function PushBonusCode(uint c) public {
         bonusCodes.push(c);
     }

     function PopBonusCode() public {
         // <yes> <report> ACCESS_CONTROL
         require(0 <= bonusCodes.length); // this condition is always true since array lengths are unsigned
         bonusCodes.length--; // an underflow can be caused here
     }

     function UpdateBonusCodeAt(uint idx, uint c) public {
         require(idx < bonusCodes.length);
         bonusCodes[idx] = c; // write to any index less than bonusCodes.length
     }

     function Destroy() public {
         require(msg.sender == owner);
         selfdestruct(msg.sender);
     }
 }
```
