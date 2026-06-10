package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Transforms a CustomerRecord into a ReportRecord.
 * Enriches customer data with account totals from CUSTSCHEMA.ACCOUNT_TABLE.
 */
@Component
public class CustomerProcessor implements ItemProcessor<CustomerRecord, ReportRecord> {

    private static final Logger log = LoggerFactory.getLogger(CustomerProcessor.class);

    private static final String ACCOUNT_SUMMARY_SQL =
            "SELECT " +
            "    COUNT(*)          AS ACCOUNT_COUNT, " +
            "    SUM(ACCT_BALANCE) AS TOTAL_BALANCE " +
            "FROM CUSTSCHEMA.ACCOUNT_TABLE " +
            "WHERE ACCT_CUST_ID = ? " +
            "  AND ACCT_STATUS  = 'A'";

    private final JdbcTemplate customerJdbc;

    @Autowired
    public CustomerProcessor(
            @Qualifier("customerDataSource") DataSource customerDataSource) {
        this.customerJdbc = new JdbcTemplate(customerDataSource);
    }

    @Override
    public ReportRecord process(CustomerRecord customer) {
        log.debug("Processing customer: {}", customer.getCustId());

        AccountSummary summary = customerJdbc.queryForObject(
                ACCOUNT_SUMMARY_SQL,
                (rs, rowNum) -> new AccountSummary(
                        rs.getInt("ACCOUNT_COUNT"),
                        rs.getBigDecimal("TOTAL_BALANCE")),
                customer.getCustId());

        if (summary == null || summary.accountCount() == 0) {
            log.warn("No active accounts for customer {}, skipping", customer.getCustId());
            return null;  // filtered out by Spring Batch
        }

        ReportRecord report = new ReportRecord();
        report.setCustId(customer.getCustId());
        report.setFullName(customer.getCustLastName() + ", " + customer.getCustFirstName());
        report.setSegment(customer.getCustSegment());
        report.setTotalBalance(summary.totalBalance());
        report.setAccountCount(summary.accountCount());
        report.setStatus(customer.getCustStatus());
        report.setReportDate(LocalDate.now());
        return report;
    }

    record AccountSummary(int accountCount, BigDecimal totalBalance) {}
}
