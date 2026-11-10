package com.mirs.agent.business.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class AuthSecurityTests {
    @Autowired MockMvc mvc;
    @Autowired JwtService jwt;
    @Autowired JdbcTemplate jdbc;
    @Autowired PasswordEncoder passwords;
    @Autowired ObjectMapper json;
    @MockitoBean AuthRedis redis;
    Actor first = new Actor("company_001", "U1001", "test-first", "CUSTOMER");
    Actor second = new Actor("company_001", "U2002", "test-second", "CUSTOMER");
    @BeforeEach void setup() {
        jdbc.update("DELETE FROM auth_accounts");
        for (Actor actor : List.of(first, second)) jdbc.update("INSERT INTO auth_accounts VALUES (?, ?, ?, ?, ?, TRUE)", actor.username(), actor.tenantId(), actor.userId(), passwords.encode("test-password-123"), actor.role());
        when(redis.allowLogin(anyString(), anyString())).thenReturn(true);
        doReturn(false).when(redis).revoked(any());
    }
    String bearer(Actor actor) { return "Bearer " + jwt.issue(actor).getTokenValue(); }
    @Test void noTokenCannotUseForgedHeadersOrInternalTokenOnPublicRoute() throws Exception {
        mvc.perform(get("/api/v1/orders/A1001").header("X-Tenant-Id", "company_001").header("X-User-Id", "U1001")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/orders/A1001").header("X-Internal-Service-Token", "test-internal-service-token-1234567890")).andExpect(status().isUnauthorized());
    }
    @Test void loginMeAndSpoofedIdentityHeaders() throws Exception {
        var body = mvc.perform(post("/api/v1/auth/login").contentType("application/json").content(json.writeValueAsString(Map.of("username", first.username(), "password", "test-password-123"))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.user.userId").value("U1001")).andReturn().getResponse().getContentAsString();
        String token = json.readTree(body).get("access_token").asText();
        assertNotNull(jwt.verify(token).getId());
        mvc.perform(get("/api/v1/auth/me").header("Authorization", "Bearer " + token)).andExpect(status().isOk()).andExpect(jsonPath("$.username").value(first.username()));
        mvc.perform(get("/api/v1/orders/A1001").header("Authorization", "Bearer " + token).header("X-User-Id", "U2002").header("X-Tenant-Id", "company_999"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.orderId").value("A1001"));
    }
    @Test void otherUserAndTenantCannotReadOrder() throws Exception {
        mvc.perform(get("/api/v1/orders/A1001").header("Authorization", bearer(second)).header("X-User-Id", "U1001")).andExpect(status().isNotFound());
        Actor foreign = new Actor("company_999", "U1001", "foreign", "CUSTOMER");
        jdbc.update("INSERT INTO auth_accounts VALUES (?, ?, ?, ?, ?, TRUE)", foreign.username(), foreign.tenantId(), foreign.userId(), passwords.encode("test-password-123"), foreign.role());
        mvc.perform(get("/api/v1/orders/A1001").header("Authorization", bearer(foreign))).andExpect(status().isNotFound());
    }
    @Test void invalidPasswordAndRateLimitDoNotIssueToken() throws Exception {
        mvc.perform(post("/api/v1/auth/login").contentType("application/json").content("{\"username\":\"test-first\",\"password\":\"bad\"}"))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.access_token").doesNotExist());
        when(redis.allowLogin(anyString(), anyString())).thenReturn(false);
        mvc.perform(post("/api/v1/auth/login").contentType("application/json").content("{\"username\":\"test-first\",\"password\":\"bad\"}"))
                .andExpect(status().isTooManyRequests());
    }
    @Test void logoutRevokesOnlyTheCurrentJtiAndNewLoginIsIndependent() throws Exception {
        Jwt old = jwt.issue(first), fresh = jwt.issue(first);
        assertNotEquals(old.getId(), fresh.getId());
        mvc.perform(post("/api/v1/auth/logout").header("Authorization", "Bearer " + old.getTokenValue())).andExpect(status().isOk());
        verify(redis).revoke(argThat(t -> t.getId().equals(old.getId())));
        when(redis.revoked(any())).thenAnswer(i -> ((Jwt)i.getArgument(0)).getId().equals(old.getId()));
        mvc.perform(get("/api/v1/auth/me").header("Authorization", "Bearer " + old.getTokenValue())).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/auth/me").header("Authorization", "Bearer " + fresh.getTokenValue())).andExpect(status().isOk());
    }
    @Test void tamperedExpiredAndWrongAudienceTokensAreRejected() throws Exception {
        String token = jwt.issue(first).getTokenValue();
        String[] parts = token.split("\\."); parts[1] = java.util.Base64.getUrlEncoder().withoutPadding().encodeToString("{\"sub\":\"attacker\"}".getBytes(StandardCharsets.UTF_8));
        mvc.perform(get("/api/v1/auth/me").header("Authorization", "Bearer " + String.join(".", parts))).andExpect(status().isUnauthorized());
        var encoder = new NimbusJwtEncoder(new ImmutableSecret<>(new SecretKeySpec("test-only-jwt-secret-at-least-32-characters".getBytes(StandardCharsets.UTF_8), "HmacSHA256")));
        for (boolean expired : List.of(true, false)) {
            var claims = JwtClaimsSet.builder().issuer("support-business").audience(List.of(expired ? "support-web" : "wrong-audience")).subject(first.username()).id(UUID.randomUUID().toString()).issuedAt(Instant.now().minusSeconds(300)).expiresAt(Instant.now().plusSeconds(expired ? -1 : 300)).build();
            String invalid = encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims)).getTokenValue();
            mvc.perform(get("/api/v1/auth/me").header("Authorization", "Bearer " + invalid)).andExpect(status().isUnauthorized());
        }
    }
    @Test void disabledAccountAndInsufficientRoleAreDenied() throws Exception {
        String token = bearer(first);
        jdbc.update("UPDATE auth_accounts SET enabled=FALSE WHERE username=?", first.username());
        mvc.perform(get("/api/v1/auth/me").header("Authorization", token)).andExpect(status().isUnauthorized());
        jdbc.update("UPDATE auth_accounts SET enabled=TRUE, role='VIEWER' WHERE username=?", first.username());
        mvc.perform(get("/api/v1/orders/A1001").header("Authorization", bearer(new Actor(first.tenantId(), first.userId(), first.username(), "VIEWER")))).andExpect(status().isForbidden());
    }
    @Test void internalEndpointNeedsServiceCredentialAndStillChecksOwnership() throws Exception {
        mvc.perform(get("/internal/v1/orders/A1001").header("Authorization", bearer(first))).andExpect(status().isUnauthorized());
        mvc.perform(get("/internal/v1/orders/A1001").header("X-Internal-Service-Token", "test-internal-service-token-1234567890").header("X-Tenant-Id", "company_001").header("X-User-Id", "U1001")).andExpect(status().isOk());
        mvc.perform(get("/internal/v1/orders/A1001").header("X-Internal-Service-Token", "test-internal-service-token-1234567890").header("X-Tenant-Id", "company_001").header("X-User-Id", "U2002")).andExpect(status().isNotFound());
    }
    @Test void blacklistFailureFailsClosedAndLogoutDoesNotPretendSuccess() throws Exception {
        when(redis.revoked(any())).thenThrow(new org.springframework.data.redis.RedisConnectionFailureException("test down"));
        mvc.perform(get("/api/v1/orders/A1001").header("Authorization", bearer(first))).andExpect(status().isServiceUnavailable());
        doReturn(false).when(redis).revoked(any());
        doThrow(new org.springframework.data.redis.RedisConnectionFailureException("test down")).when(redis).revoke(any());
        mvc.perform(post("/api/v1/auth/logout").header("Authorization", bearer(first))).andExpect(status().isServiceUnavailable());
    }
}
