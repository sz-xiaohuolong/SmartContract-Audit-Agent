package com.xhl.audit.gateway;

import com.xhl.audit.support.RiskCatalogFixture;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HypothesisSchemaTest {
    @Test void 模型操作字段只允许调用与写入且不暴露后端事实字段() throws Exception {
        var schema = RiskCatalogFixture.MAPPER.readTree(SpringAiGateway.hypothesisSchema());
        var item = schema.path("properties").path("hypotheses").path("items");
        assertEquals(RiskCatalogFixture.MAPPER.readTree("[\"CALL\",\"WRITE\"]"),
            item.path("properties").path("riskOperation").path("enum"));
        assertEquals(7, item.path("properties").size());
        assertFalse(item.path("properties").has("riskFactId"));
        assertFalse(item.path("additionalProperties").asBoolean());
    }
}
