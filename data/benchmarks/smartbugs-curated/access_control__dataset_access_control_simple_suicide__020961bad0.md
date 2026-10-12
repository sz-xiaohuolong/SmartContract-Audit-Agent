---
Dataset: smartbugs-curated
Name: simple_suicide.sol
Category: access_control
Pragma: 0.4.0
Origin-Path: dataset/access_control/simple_suicide.sol
Source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/unprotected_critical_functions/simple_suicide.sol
Vulnerable-Lines: 12, 13
---

# Vulnerability Reference Case: access_control

## Source Code
```solidity
/*
 * @source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/unprotected_critical_functions/simple_suicide.sol
 * @author: -
 * @vulnerable_at_lines: 12,13
 */

//added prgma version
pragma solidity ^0.4.0;

contract SimpleSuicide {
  // <yes> <report> ACCESS_CONTROL
  function sudicideAnyone() {
    selfdestruct(msg.sender);
  }

}
```
