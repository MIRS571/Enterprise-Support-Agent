package com.mirs.agent.business.auth;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.Optional;

@Repository
public class AccountRepository {
    public record Account(Actor actor, String passwordHash, boolean enabled) { }
    private final JdbcTemplate jdbc;
    public AccountRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public Optional<Account> find(String username) {
        return jdbc.query("SELECT * FROM auth_accounts WHERE username = ?", (r, i) ->
                new Account(new Actor(r.getString("tenant_id"), r.getString("user_id"), r.getString("username"), r.getString("role")),
                        r.getString("password_hash"), r.getBoolean("enabled")), username).stream().findFirst();
    }
    public Optional<Account> findIdentity(String tenant, String user) {
        return jdbc.query("SELECT username FROM auth_accounts WHERE tenant_id = ? AND user_id = ?",
                (r, i) -> r.getString(1), tenant, user).stream().findFirst().flatMap(this::find);
    }
    public void insertIfMissing(String username, String userId, String passwordHash) {
        if (find(username).isEmpty()) jdbc.update("INSERT INTO auth_accounts(username, tenant_id, user_id, password_hash, role, enabled) VALUES (?, 'company_001', ?, ?, 'CUSTOMER', TRUE)", username, userId, passwordHash);
    }
}
