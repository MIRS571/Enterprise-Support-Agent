package com.mirs.agent.business.auth;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

@Service
public class AuthRedis {
    private final StringRedisTemplate redis;
    public AuthRedis(StringRedisTemplate redis) { this.redis = redis; }
    public boolean revoked(Jwt jwt) { return Boolean.TRUE.equals(redis.hasKey(key(jwt))); }
    public void revoke(Jwt jwt) {
        Duration remaining = Duration.between(Instant.now(), jwt.getExpiresAt());
        if (!remaining.isNegative() && !remaining.isZero()) redis.opsForValue().set(key(jwt), "1", remaining);
    }
    private String key(Jwt jwt) { return "esa:auth:revoked:" + jwt.getId(); }
    public boolean allowLogin(String remoteAddress, String username) {
        var script = new DefaultRedisScript<Long>("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n", Long.class);
        Long ip = redis.execute(script, List.of("esa:auth:login:ip:" + hash(remoteAddress)));
        Long account = redis.execute(script, List.of("esa:auth:login:user:" + hash(username)));
        return ip != null && account != null && ip <= 100 && account <= 20;
    }
    private String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
