// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract MythrilDemo {

    // 场景 1: 整数溢出 (Integer Overflow)
    // Mythril 会通过符号执行发现：存在 a + b > 255 的情况导致回绕
    function test_overflow(uint8 a, uint8 b) public pure returns (uint8) {
        unchecked {
            return a + b;
        }
    }

    // 场景 2: 路径探索 (Path Exploration)
    // 这是一个"海森堡Bug"，只有当输入特定的“密码”时才会触发。
    // Slither 通常只会报"看起来有断言"，但 Mythril 能精确计算出 input = 123456789 时会崩溃。
    function solve_me(uint256 input) public pure {
        if (input == 123456789) {
            // 触发断言失败
            assert(false);
        }
    }
}