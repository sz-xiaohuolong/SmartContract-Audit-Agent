---
Dataset: smartbugs-curated
Name: mishandled.sol
Category: unchecked_low_level_calls
Pragma: 0.4.0
Origin-Path: dataset/unchecked_low_level_calls/mishandled.sol
Source: https://github.com/seresistvanandras/EthBench/blob/master/Benchmark/Simple/mishandled.sol
Vulnerable-Lines: 14
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: https://github.com/seresistvanandras/EthBench/blob/master/Benchmark/Simple/mishandled.sol 
 * @author: -
 * @vulnerable_at_lines: 14
 */

pragma solidity ^0.4.0;
contract SendBack {
    mapping (address => uint) userBalances;
    function withdrawBalance() {  
		uint amountToWithdraw = userBalances[msg.sender];
		userBalances[msg.sender] = 0;
        // <yes> <report> UNCHECKED_LL_CALLS
		msg.sender.send(amountToWithdraw);
	}
}
```
