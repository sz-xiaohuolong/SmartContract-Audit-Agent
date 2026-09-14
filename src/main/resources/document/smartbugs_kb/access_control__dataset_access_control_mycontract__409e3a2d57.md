---
Dataset: smartbugs-curated
Name: mycontract.sol
Category: access_control
Pragma: 0.4.24
Origin-Path: dataset/access_control/mycontract.sol
Source: https://consensys.github.io/smart-contract-best-practices/recommendations/#avoid-using-txorigin
Vulnerable-Lines: 20
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://consensys.github.io/smart-contract-best-practices/recommendations/#avoid-using-txorigin
 * @author: Consensys Diligence
 * @vulnerable_at_lines: 20
 * Modified by Gerhard Wagner
 */

pragma solidity ^0.4.24;

contract MyContract {

    address owner;

    function MyContract() public {
        owner = msg.sender;
    }

    function sendTo(address receiver, uint amount) public {
        // <yes> <report> ACCESS_CONTROL
        require(tx.origin == owner);
        receiver.transfer(amount);
    }

}
```
