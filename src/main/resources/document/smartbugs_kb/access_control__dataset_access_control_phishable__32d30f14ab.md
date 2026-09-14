---
Dataset: smartbugs-curated
Name: phishable.sol
Category: access_control
Pragma: 0.4.22
Origin-Path: dataset/access_control/phishable.sol
Source: https://github.com/sigp/solidity-security-blog
Vulnerable-Lines: 20
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://github.com/sigp/solidity-security-blog
 * @author: -
 * @vulnerable_at_lines: 20
 */

 pragma solidity ^0.4.22;

 contract Phishable {
    address public owner;

    constructor (address _owner) {
        owner = _owner;
    }

    function () public payable {} // collect ether

    function withdrawAll(address _recipient) public {
        // <yes> <report> ACCESS_CONTROL
        require(tx.origin == owner);
        _recipient.transfer(this.balance);
    }
}
```
