pragma solidity ^0.8.0;

contract VulnerableDonation {
    mapping (address => uint) public balances;
    address payable public owner;

    constructor() {
        owner = payable(msg.sender);
    }

    function donate() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint _amount) public {
        // 这是一个经典的重入攻击漏洞（先转账，后扣款）
        require(balances[msg.sender] >= _amount, "Insufficient balance");
        payable(msg.sender).transfer(_amount);
        balances[msg.sender] -= _amount;
    }
}