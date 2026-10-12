---
Dataset: smartbugs-curated
Name: proxy.sol
Category: access_control
Pragma: 0.4.24
Origin-Path: dataset/access_control/proxy.sol
Source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-112#proxysol
Vulnerable-Lines: 19
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://smartcontractsecurity.github.io/SWC-registry/docs/SWC-112#proxysol
 * @author: -
 * @vulnerable_at_lines: 19
 */

pragma solidity ^0.4.24;

contract Proxy {

  address owner;

  constructor() public {
    owner = msg.sender;
  }

  function forward(address callee, bytes _data) public {
    // <yes> <report> ACCESS_CONTROL
    require(callee.delegatecall(_data)); //Use delegatecall with caution and make sure to never call into untrusted contracts
  }

}
```
