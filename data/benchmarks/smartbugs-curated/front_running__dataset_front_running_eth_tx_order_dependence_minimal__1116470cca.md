---
Dataset: smartbugs-curated
Name: eth_tx_order_dependence_minimal.sol
Category: front_running
Pragma: 0.4.16
Origin-Path: dataset/front_running/eth_tx_order_dependence_minimal.sol
Source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
Vulnerable-Lines: 23, 31
---

# Vulnerability Reference Case: front_running

## Source Code
```solidity
/*
 * @source: https://github.com/ConsenSys/evm-analyzer-benchmark-suite
 * @author: Suhabe Bugrara
 * @vulnerable_at_lines: 23,31
 */

pragma solidity ^0.4.16;

contract EthTxOrderDependenceMinimal {
    address public owner;
    bool public claimed;
    uint public reward;

    function EthTxOrderDependenceMinimal() public {
        owner = msg.sender;
    }

    function setReward() public payable {
        require (!claimed);

        require(msg.sender == owner);
        // <yes> <report> FRONT_RUNNING
        owner.transfer(reward);
        reward = msg.value;
    }

    function claimReward(uint256 submission) {
        require (!claimed);
        require(submission < 10);
        // <yes> <report> FRONT_RUNNING
        msg.sender.transfer(reward);
        claimed = true;
    }
}
```
