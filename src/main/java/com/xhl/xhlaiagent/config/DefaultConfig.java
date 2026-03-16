package com.xhl.xhlaiagent.config;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * 默认配置
 * <p>
 * 在非 coding-plan profile 下，排除 OpenAI 自动配置，避免与 Dashscope 冲突。
 * </p>
 */
@Configuration
@Profile("!coding-plan")
@EnableAutoConfiguration(excludeName = {
        "org.springframework.ai.autoconfigure.openai.OpenAiAutoConfiguration"
})
public class DefaultConfig {
}