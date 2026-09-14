---
Dataset: smartbugs-curated
Name: unprotected0.sol
Category: access_control
Pragma: 0.4.15
Origin-Path: dataset/access_control/unprotected0.sol
Source: https://github.com/trailofbits/not-so-smart-contracts/blob/master/unprotected_function/Unprotected.sol
Vulnerable-Lines: 25
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://github.com/trailofbits/not-so-smart-contracts/blob/master/unprotected_function/Unprotected.sol
 * @author: -
 * @vulnerable_at_lines: 25
 */

 pragma solidity ^0.4.15;

 contract Unprotected{
     address private owner;

     modifier onlyowner {
         require(msg.sender==owner);
         _;
     }

     function Unprotected()
         public
     {
         owner = msg.sender;
     }

     // This function should be protected
     // <yes> <report> ACCESS_CONTROL
     function changeOwner(address _newOwner)
         public
     {
        owner = _newOwner;
     }

    /*
    function changeOwner_fixed(address _newOwner)
         public
         onlyowner
     {
        owner = _newOwner;
     }
     */
 }
```
