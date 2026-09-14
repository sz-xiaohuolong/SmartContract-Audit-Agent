---
Dataset: smartbugs-curated
Name: insecure_transfer.sol
Category: arithmetic
Pragma: 0.4.10
Origin-Path: dataset/arithmetic/insecure_transfer.sol
Source: https://consensys.github.io/smart-contract-best-practices/known_attacks/#front-running-aka-transaction-ordering-dependence
Vulnerable-Lines: 18
---

# Vulnerability Reference Case: arithmetic

## Source Code
```solidity
/*
 * @source: https://consensys.github.io/smart-contract-best-practices/known_attacks/#front-running-aka-transaction-ordering-dependence
 * @author: consensys
 * @vulnerable_at_lines: 18
 */

pragma solidity ^0.4.10;

contract IntegerOverflowAdd {
    mapping (address => uint256) public balanceOf;

    // INSECURE
    function transfer(address _to, uint256 _value) public{
        /* Check if sender has balance */
        require(balanceOf[msg.sender] >= _value);
        balanceOf[msg.sender] -= _value;
        // <yes> <report> ARITHMETIC
        balanceOf[_to] += _value;
}

}
```
