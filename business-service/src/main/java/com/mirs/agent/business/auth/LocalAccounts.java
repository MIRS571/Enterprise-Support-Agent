package com.mirs.agent.business.auth;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/** Explicit opt-in bootstrap for local demo accounts. No shared default password. */
@Component
@ConditionalOnProperty(name = "auth.bootstrap-enabled", havingValue = "true")
public class LocalAccounts implements ApplicationRunner {
    private final AccountRepository accounts;
    private final PasswordEncoder passwords;
    private final String first;
    private final String second;
    public LocalAccounts(AccountRepository accounts, PasswordEncoder passwords,
            @Value("${auth.bootstrap-password}") String first,
            @Value("${auth.bootstrap-second-password}") String second) {
        this.accounts = accounts; this.passwords = passwords; this.first = first; this.second = second;
    }
    @Override public void run(ApplicationArguments args) {
        if (first.length() < 12 || second.length() < 12) throw new IllegalStateException("Local bootstrap passwords must be at least 12 characters");
        accounts.insertIfMissing("customer1", "U1001", passwords.encode(first));
        accounts.insertIfMissing("customer2", "U2002", passwords.encode(second));
    }
}
