---
Dataset: smartbugs-curated
Name: guess_the_random_number.sol
Category: bad_randomness
Pragma: 0.4.21
Origin-Path: dataset/bad_randomness/guess_the_random_number.sol
Source: https://capturetheether.com/challenges/lotteries/guess-the-random-number/
Vulnerable-Lines: 15
---

# Vulnerability Reference Case: bad_randomness

## Source Code
```solidity
/*
 * @source: https://capturetheether.com/challenges/lotteries/guess-the-random-number/
 * @author: Steve Marx
 * @vulnerable_at_lines: 15
 */

pragma solidity ^0.4.21;

contract GuessTheRandomNumberChallenge {
    uint8 answer;

    function GuessTheRandomNumberChallenge() public payable {
        require(msg.value == 1 ether);
        // <yes> <report> BAD_RANDOMNESS
        answer = uint8(keccak256(block.blockhash(block.number - 1), now));
    }

    function isComplete() public view returns (bool) {
        return address(this).balance == 0;
    }

    function guess(uint8 n) public payable {
        require(msg.value == 1 ether);

        if (n == answer) {
            msg.sender.transfer(2 ether);
        }
    }
}
```
