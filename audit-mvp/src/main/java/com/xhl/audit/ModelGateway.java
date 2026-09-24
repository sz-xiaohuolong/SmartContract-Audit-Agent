package com.xhl.audit;

@FunctionalInterface
public interface ModelGateway {
    GatewayReply complete(String provider, String system, String user);
}
