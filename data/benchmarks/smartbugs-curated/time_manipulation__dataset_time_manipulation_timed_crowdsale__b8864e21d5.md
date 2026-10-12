---
Dataset: smartbugs-curated
Name: timed_crowdsale.sol
Category: time_manipulation
Pragma: 0.4.25
Origin-Path: dataset/time_manipulation/timed_crowdsale.sol
Source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/timestamp_dependence/timed_crowdsale.sol
Vulnerable-Lines: 13
---

# Vulnerability Reference Case: time_manipulation

## Source Code
```solidity
/*
 * @source: https://github.com/SmartContractSecurity/SWC-registry/blob/master/test_cases/timestamp_dependence/timed_crowdsale.sol
 * @author: -
 * @vulnerable_at_lines: 13
 */

pragma solidity ^0.4.25;

contract TimedCrowdsale {
  // Sale should finish exactly at January 1, 2019
  function isSaleFinished() view public returns (bool) {
    // <yes> <report> TIME_MANIPULATION
    return block.timestamp >= 1546300800;
  }
}
```
