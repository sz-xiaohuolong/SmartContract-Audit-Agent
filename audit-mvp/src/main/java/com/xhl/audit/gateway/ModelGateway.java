package com.xhl.audit.gateway;

import com.xhl.audit.dto.GatewayReply;

@FunctionalInterface
public interface ModelGateway {
    GatewayReply complete(String provider, String system, String user);
}
