---
Dataset: smartbugs-curated
Name: 0xf2570186500a46986f3139f65afedc2afe4f445d.sol
Category: unchecked_low_level_calls
Pragma: 0.4.16
Origin-Path: dataset/unchecked_low_level_calls/0xf2570186500a46986f3139f65afedc2afe4f445d.sol
Source: etherscan.io
Vulnerable-Lines: 18
---

# Vulnerability Reference Case: unchecked_low_level_calls

## Source Code
```solidity
/*
 * @source: etherscan.io 
 * @author: -
 * @vulnerable_at_lines: 18
 */

pragma solidity ^0.4.16;

contract RealOldFuckMaker {
    address fuck = 0xc63e7b1DEcE63A77eD7E4Aeef5efb3b05C81438D;
    
    // this can make OVER 9,000 OLD FUCKS
    // (just pass in 129)
    function makeOldFucks(uint32 number) {
        uint32 i;
        for (i = 0; i < number; i++) {
            // <yes> <report> UNCHECKED_LL_CALLS
            fuck.call(bytes4(sha3("giveBlockReward()")));
        }
    }
}
```
