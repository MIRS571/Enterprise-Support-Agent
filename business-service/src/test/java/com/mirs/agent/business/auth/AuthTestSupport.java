package com.mirs.agent.business.auth;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import java.util.List;

public final class AuthTestSupport {
    public static RequestPostProcessor user(String tenant, String user) {
        return SecurityMockMvcRequestPostProcessors.authentication(new UsernamePasswordAuthenticationToken(
                new Actor(tenant, user, "test-user", "CUSTOMER"), null, List.of(new SimpleGrantedAuthority("ROLE_CUSTOMER"))));
    }
}
