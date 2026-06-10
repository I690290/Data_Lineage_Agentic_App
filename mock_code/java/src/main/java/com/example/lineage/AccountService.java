package com.example.lineage;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * AccountService — reads ACCOUNT_SUMMARY table via JDBC and MONTHLY_REPORT view.
 * Consumes data written by COBOL PROG001 → SQL load_accounts.sql pipeline.
 */
@Service
public class AccountService {

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    /**
     * Find an account by its account number.
     * Reads from ACCOUNT_SUMMARY table (populated by load_accounts.sql).
     */
    public Optional<AccountSummary> findByAccountNumber(Long accountNumber) {
        return accountRepository.findByAccountNumber(accountNumber);
    }

    /**
     * Get monthly report for an account from the MONTHLY_REPORT view.
     * This view joins ACCOUNT_SUMMARY with TRANSACTION_DETAIL.
     */
    public List<Map<String, Object>> getMonthlyReport(Long accountNumber, int year, int month) {
        String sql = """
                SELECT ACCOUNT_NUMBER, CUSTOMER_NAME, ACCOUNT_TYPE,
                       BRANCH_CODE, PRODUCT_CODE, CURRENT_BALANCE,
                       CREDIT_LIMIT, TRANSACTION_COUNT,
                       TOTAL_PURCHASES, TOTAL_REFUNDS, NET_SPEND,
                       AVG_RISK_SCORE, MAX_RISK_SCORE
                FROM MONTHLY_REPORT
                WHERE ACCOUNT_NUMBER = ?
                  AND REPORT_YEAR    = ?
                  AND REPORT_MONTH   = ?
                """;
        return jdbcTemplate.queryForList(sql, accountNumber, year, month);
    }

    /**
     * Get all active accounts with high risk scores from ACCOUNT_SUMMARY.
     */
    @Transactional(readOnly = true)
    public List<AccountSummary> getHighRiskAccounts(double riskThreshold) {
        String sql = """
                SELECT a.ACCOUNT_NUMBER, a.CUSTOMER_NAME, a.ACCOUNT_TYPE,
                       a.BALANCE, a.STATUS_CODE, a.CREDIT_LIMIT,
                       a.BRANCH_CODE, a.PRODUCT_CODE
                FROM ACCOUNT_SUMMARY a
                WHERE a.STATUS_CODE = 'AC'
                  AND EXISTS (
                      SELECT 1 FROM TRANSACTION_DETAIL t
                      WHERE t.ACCOUNT_NUMBER = a.ACCOUNT_NUMBER
                        AND t.RISK_SCORE > ?
                  )
                ORDER BY a.ACCOUNT_NUMBER
                """;
        return jdbcTemplate.query(sql, new AccountSummaryRowMapper(), riskThreshold);
    }

    /**
     * Update account status in ACCOUNT_SUMMARY table.
     */
    @Transactional
    public int updateAccountStatus(Long accountNumber, String statusCode) {
        String sql = "UPDATE ACCOUNT_SUMMARY SET STATUS_CODE = ?, LAST_UPDATED = CURRENT_TIMESTAMP WHERE ACCOUNT_NUMBER = ?";
        return jdbcTemplate.update(sql, statusCode, accountNumber);
    }

    // ------- inner row mapper -------

    private static class AccountSummaryRowMapper implements RowMapper<AccountSummary> {
        @Override
        public AccountSummary mapRow(ResultSet rs, int rowNum) throws SQLException {
            AccountSummary a = new AccountSummary();
            a.setAccountNumber(rs.getLong("ACCOUNT_NUMBER"));
            a.setCustomerName(rs.getString("CUSTOMER_NAME"));
            a.setAccountType(rs.getString("ACCOUNT_TYPE"));
            a.setBalance(rs.getBigDecimal("BALANCE"));
            a.setStatusCode(rs.getString("STATUS_CODE"));
            a.setCreditLimit(rs.getBigDecimal("CREDIT_LIMIT"));
            a.setBranchCode(rs.getString("BRANCH_CODE"));
            a.setProductCode(rs.getString("PRODUCT_CODE"));
            return a;
        }
    }
}
