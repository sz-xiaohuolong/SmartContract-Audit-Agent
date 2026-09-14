---
Dataset: smartbugs-curated
Name: short_address_example.sol
Category: short_addresses
Pragma: 0.4.11
Origin-Path: dataset/short_addresses/short_address_example.sol
Source: https://ericrafaloff.com/analyzing-the-erc20-short-address-attack/
Vulnerable-Lines: 18
---

# Vulnerability Reference Case: short_addresses

## Source Code
```solidity
/*
 * @source: https://ericrafaloff.com/analyzing-the-erc20-short-address-attack/
 * @author: -
 * @vulnerable_at_lines: 18
 */

 pragma solidity ^0.4.11;

 contract MyToken {
     mapping (address => uint) balances;

     event Transfer(address indexed _from, address indexed _to, uint256 _value);

     function MyToken() {
         balances[tx.origin] = 10000;
     }
     // <yes> <report> SHORT_ADDRESSES
     function sendCoin(address to, uint amount) returns(bool sufficient) {
         if (balances[msg.sender] < amount) return false;
         balances[msg.sender] -= amount;
         balances[to] += amount;
         Transfer(msg.sender, to, amount);
         return true;
     }

     function getBalance(address addr) constant returns(uint) {
         return balances[addr];
     }
 }
```
