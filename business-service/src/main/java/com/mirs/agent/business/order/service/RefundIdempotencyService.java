package com.mirs.agent.business.order.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mirs.agent.business.order.dto.OrderResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.function.Supplier;

@Service
public class RefundIdempotencyService {

    private static final String ACQUIRED = "__ACQUIRED__";
    private static final DefaultRedisScript<String> CLAIM_SCRIPT =
            new DefaultRedisScript<>("""
                    local existing = redis.call('GET', KEYS[1])
                    if existing then
                        return existing
                    end
                    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
                    return '__ACQUIRED__'
                    """, String.class);
    private static final DefaultRedisScript<Long> COMPLETE_SCRIPT =
            new DefaultRedisScript<>("""
                    if redis.call('GET', KEYS[1]) == ARGV[1] then
                        redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
                        return 1
                    end
                    return 0
                    """, Long.class);
    private static final DefaultRedisScript<Long> RELEASE_SCRIPT =
            new DefaultRedisScript<>("""
                    if redis.call('GET', KEYS[1]) == ARGV[1] then
                        return redis.call('DEL', KEYS[1])
                    end
                    return 0
                    """, Long.class);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final String keyPrefix;
    private final String environment;
    private final long processingTtlSeconds;
    private final long completedTtlSeconds;

    public RefundIdempotencyService(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            @Value("${business.refund-idempotency.key-prefix}") String keyPrefix,
            @Value("${business.environment}") String environment,
            @Value("${business.refund-idempotency.processing-ttl-seconds}")
            long processingTtlSeconds,
            @Value("${business.refund-idempotency.completed-ttl-seconds}")
            long completedTtlSeconds
    ) {
        if (processingTtlSeconds < 1 || completedTtlSeconds < 1) {
            throw new IllegalArgumentException("幂等记录 TTL 必须大于 0");
        }
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.keyPrefix = keyPrefix;
        this.environment = environment;
        this.processingTtlSeconds = processingTtlSeconds;
        this.completedTtlSeconds = completedTtlSeconds;
    }

    public OrderResponse execute(
            String tenantId,
            String userId,
            String orderId,
            String idempotencyKey,
            Supplier<OrderResponse> action
    ) {
        String key = String.join(
                ":",
                keyPrefix,
                environment,
                "idempotency",
                "refund",
                tenantId,
                userId,
                idempotencyKey
        );
        String fingerprint = "request_refund:" + orderId;
        StoredRecord processingRecord = new StoredRecord(
                fingerprint,
                IdempotencyStatus.PROCESSING,
                null
        );
        String processingJson = writeRecord(processingRecord);
        String claimResult;
        try {
            claimResult = redisTemplate.execute(
                    CLAIM_SCRIPT,
                    List.of(key),
                    processingJson,
                    Long.toString(processingTtlSeconds)
            );
        } catch (DataAccessException exception) {
            throw new IdempotencyUnavailableException(
                    "退款幂等服务暂时不可用",
                    exception
            );
        }

        if (!ACQUIRED.equals(claimResult)) {
            return handleExisting(claimResult, fingerprint);
        }

        OrderResponse response;
        try {
            response = action.get();
        } catch (RuntimeException exception) {
            releaseQuietly(key, processingJson);
            throw exception;
        }

        StoredRecord completedRecord = new StoredRecord(
                fingerprint,
                IdempotencyStatus.COMPLETED,
                response
        );
        String completedJson = writeRecord(completedRecord);
        try {
            Long completed = redisTemplate.execute(
                    COMPLETE_SCRIPT,
                    List.of(key),
                    processingJson,
                    completedJson,
                    Long.toString(completedTtlSeconds)
            );
            if (!Long.valueOf(1L).equals(completed)) {
                throw new IdempotencyOutcomeUnknownException(
                        "退款已执行，但幂等结果未能确认"
                );
            }
        } catch (DataAccessException exception) {
            throw new IdempotencyOutcomeUnknownException(
                    "退款已执行，但幂等结果保存失败",
                    exception
            );
        }
        return response;
    }

    private OrderResponse handleExisting(
            String claimResult,
            String fingerprint
    ) {
        StoredRecord existing = readRecord(claimResult);
        if (!fingerprint.equals(existing.fingerprint())) {
            throw new IdempotencyConflictException();
        }
        if (existing.status() == IdempotencyStatus.PROCESSING) {
            throw new IdempotencyInProgressException();
        }
        if (existing.response() == null) {
            throw new IdempotencyUnavailableException(
                    "已完成的幂等记录缺少响应"
            );
        }
        return existing.response();
    }

    private void releaseQuietly(String key, String processingJson) {
        try {
            redisTemplate.execute(
                    RELEASE_SCRIPT,
                    List.of(key),
                    processingJson
            );
        } catch (DataAccessException ignored) {
            // PROCESSING has a short TTL and will expire automatically.
        }
    }

    private String writeRecord(StoredRecord record) {
        try {
            return objectMapper.writeValueAsString(record);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("无法序列化退款幂等记录", exception);
        }
    }

    private StoredRecord readRecord(String value) {
        try {
            return objectMapper.readValue(value, StoredRecord.class);
        } catch (JsonProcessingException exception) {
            throw new IdempotencyUnavailableException(
                    "退款幂等记录格式无效",
                    exception
            );
        }
    }

    private enum IdempotencyStatus {
        PROCESSING,
        COMPLETED
    }

    private record StoredRecord(
            String fingerprint,
            IdempotencyStatus status,
            OrderResponse response
    ) {
    }
}
