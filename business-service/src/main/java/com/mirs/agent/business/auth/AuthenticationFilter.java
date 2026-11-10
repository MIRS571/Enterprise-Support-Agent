package com.mirs.agent.business.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.dao.DataAccessException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.Map;

public class AuthenticationFilter extends OncePerRequestFilter {
    private final JwtService jwt;
    private final AuthRedis redis;
    private final AccountRepository accounts;
    private final byte[] internalToken;
    private final ObjectMapper mapper;
    public AuthenticationFilter(JwtService jwt, AuthRedis redis, AccountRepository accounts, String token, ObjectMapper mapper) {
        this.jwt = jwt; this.redis = redis; this.accounts = accounts; this.mapper = mapper;
        if (token == null || token.length() < 24) throw new IllegalStateException("Internal token too short");
        internalToken = token.getBytes(StandardCharsets.UTF_8);
    }
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws IOException, ServletException {
        try {
            if (req.getRequestURI().startsWith(req.getContextPath() + "/internal/")) {
                String provided = req.getHeader("X-Internal-Service-Token");
                if (provided == null || !MessageDigest.isEqual(internalToken, provided.getBytes(StandardCharsets.UTF_8))) {
                    error(res, 401, "UNAUTHORIZED", "内部服务认证失败"); return;
                }
                SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("agent-service", null, List.of(new SimpleGrantedAuthority("ROLE_AGENT_SERVICE"))));
            } else if (req.getHeader("Authorization") != null) {
                String header = req.getHeader("Authorization");
                if (!header.startsWith("Bearer ")) { error(res, 401, "UNAUTHORIZED", "登录凭证格式错误"); return; }
                Jwt decoded = jwt.verify(header.substring(7));
                if (redis.revoked(decoded)) { error(res, 401, "UNAUTHORIZED", "登录已失效，请重新登录"); return; }
                var account = accounts.find(decoded.getSubject()).orElse(null);
                if (account == null || !account.enabled() || !account.actor().tenantId().equals(decoded.getClaimAsString("tenant_id"))
                        || !account.actor().userId().equals(decoded.getClaimAsString("user_id")) || !account.actor().role().equals(decoded.getClaimAsString("role"))) {
                    error(res, 401, "UNAUTHORIZED", "账号状态已改变，请重新登录"); return;
                }
                SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(account.actor(), decoded, List.of(new SimpleGrantedAuthority("ROLE_" + account.actor().role()))));
            }
        } catch (JwtException | IllegalArgumentException e) { error(res, 401, "UNAUTHORIZED", "登录凭证无效或已过期"); return;
        } catch (DataAccessException e) { error(res, 503, "AUTH_UNAVAILABLE", "认证服务暂时不可用，请稍后重试"); return; }
        chain.doFilter(req, res);
    }
    private void error(HttpServletResponse res, int status, String code, String message) throws IOException {
        SecurityContextHolder.clearContext(); res.setStatus(status); res.setContentType("application/json;charset=UTF-8");
        mapper.writeValue(res.getOutputStream(), Map.of("code", code, "message", message));
    }
}
