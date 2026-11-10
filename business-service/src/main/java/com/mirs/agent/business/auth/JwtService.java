package com.mirs.agent.business.auth;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Service;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public class JwtService {
    private final JwtEncoder encoder;
    private final NimbusJwtDecoder decoder;
    private final long ttl;
    public JwtService(@Value("${auth.jwt-secret}") String secret, @Value("${auth.jwt-ttl-seconds:3600}") long ttl) {
        byte[] bytes = secret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32 || ttl < 60 || ttl > 86400) throw new IllegalStateException("JWT secret/TTL configuration invalid");
        var key = new SecretKeySpec(bytes, "HmacSHA256");
        encoder = new NimbusJwtEncoder(new ImmutableSecret<>(key));
        decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
        decoder.setJwtValidator(new org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ZERO), new JwtIssuerValidator("support-business")));
        this.ttl = ttl;
    }
    public Jwt issue(Actor actor) {
        var now = Instant.now();
        var claims = JwtClaimsSet.builder().issuer("support-business").audience(List.of("support-web"))
                .subject(actor.username()).id(UUID.randomUUID().toString()).issuedAt(now).expiresAt(now.plusSeconds(ttl))
                .claim("tenant_id", actor.tenantId()).claim("user_id", actor.userId()).claim("role", actor.role()).build();
        return encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims));
    }
    public Jwt verify(String token) {
        Jwt jwt = decoder.decode(token);
        if (jwt.getExpiresAt() == null || !jwt.getExpiresAt().isAfter(Instant.now()) || jwt.getId() == null
                || jwt.getSubject() == null || !jwt.getAudience().contains("support-web")) throw new BadJwtException("Invalid claims");
        return jwt;
    }
}
