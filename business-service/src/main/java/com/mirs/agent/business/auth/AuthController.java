package com.mirs.agent.business.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
    public record LoginRequest(@NotBlank @Size(max=64) String username, @NotBlank @Size(max=128) String password) { }
    private final AccountRepository accounts;
    private final PasswordEncoder passwords;
    private final JwtService jwt;
    private final AuthRedis redis;
    private final String dummyHash;
    public AuthController(AccountRepository accounts, PasswordEncoder passwords, JwtService jwt, AuthRedis redis) {
        this.accounts = accounts; this.passwords = passwords; this.jwt = jwt; this.redis = redis;
        dummyHash = passwords.encode(java.util.UUID.randomUUID().toString());
    }
    @PostMapping("/login")
    public ResponseEntity<?> login(@Valid @RequestBody LoginRequest request, HttpServletRequest servlet) {
        String username = request.username().trim();
        if (!redis.allowLogin(servlet.getRemoteAddr(), username)) return ResponseEntity.status(429).body(Map.of("message", "登录尝试过于频繁，请稍后再试"));
        var account = accounts.find(username).orElse(null);
        boolean matched = passwords.matches(request.password(), account == null ? dummyHash : account.passwordHash());
        if (!matched || account == null || !account.enabled()) return ResponseEntity.status(401).body(Map.of("message", "用户名或密码错误"));
        Jwt token = jwt.issue(account.actor());
        return ResponseEntity.ok(Map.of("access_token", token.getTokenValue(), "token_type", "Bearer", "expires_at", token.getExpiresAt(), "user", account.actor()));
    }
    @GetMapping("/me") public Actor me(@AuthenticationPrincipal Actor actor) { return actor; }
    @PostMapping("/logout") public Map<String, String> logout(Authentication authentication) {
        redis.revoke((Jwt) authentication.getCredentials());
        return Map.of("message", "已退出登录");
    }
}
