package com.mirs.agent.business.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import java.util.Map;

@Configuration
public class SecurityConfig {
    @Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }
    @Bean SecurityFilterChain security(HttpSecurity http, JwtService jwt, AuthRedis redis, AccountRepository accounts,
            @Value("${agent-service.internal-token}") String token, ObjectMapper mapper) throws Exception {
        return http.csrf(c -> c.disable()).cors(c -> c.disable()).formLogin(c -> c.disable()).httpBasic(c -> c.disable()).logout(c -> c.disable())
                .sessionManagement(c -> c.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(c -> c.disable())
                .authorizeHttpRequests(c -> c
                        .dispatcherTypeMatchers(DispatcherType.ASYNC, DispatcherType.ERROR).permitAll()
                        .requestMatchers("/api/v1/auth/login", "/actuator/health", "/api/v1/system/info").permitAll()
                        .requestMatchers("/internal/**").hasRole("AGENT_SERVICE")
                        .requestMatchers("/api/v1/auth/me", "/api/v1/auth/logout").hasAnyRole("CUSTOMER", "ADMIN")
                        .requestMatchers("/api/v1/agent/**", "/api/v1/orders/**").hasRole("CUSTOMER")
                        .anyRequest().denyAll())
                .exceptionHandling(c -> c.authenticationEntryPoint((req, res, ex) -> {
                    res.setStatus(401); res.setContentType("application/json;charset=UTF-8");
                    mapper.writeValue(res.getOutputStream(), Map.of("code", "UNAUTHORIZED", "message", "请先登录"));
                }).accessDeniedHandler((req, res, ex) -> {
                    res.setStatus(403); res.setContentType("application/json;charset=UTF-8");
                    mapper.writeValue(res.getOutputStream(), Map.of("code", "FORBIDDEN", "message", "没有访问权限"));
                }))
                .addFilterBefore(new AuthenticationFilter(jwt, redis, accounts, token, mapper), UsernamePasswordAuthenticationFilter.class).build();
    }
}
