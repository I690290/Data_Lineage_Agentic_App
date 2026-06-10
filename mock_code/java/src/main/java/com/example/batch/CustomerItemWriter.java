package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import javax.sql.DataSource;
import java.util.List;

/**
 * Writes processed ReportRecords to RPTSCHEMA.REPORT_TABLE
 * and audit entries to RPTSCHEMA.AUDIT_LOG using the report DataSource (RPTDB).
 */
@Component
public class CustomerItemWriter implements ItemWriter<ReportRecord> {

    private static final Logger log = LoggerFactory.getLogger(CustomerItemWriter.class);

    private static final String INSERT_REPORT_SQL =
            "INSERT INTO RPTSCHEMA.REPORT_TABLE " +
            "    (CUST_ID, FULL_NAME, SEGMENT, TOTAL_BALANCE, ACCOUNT_COUNT, STATUS, REPORT_DATE) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)";

    private static final String INSERT_AUDIT_SQL =
            "INSERT INTO RPTSCHEMA.AUDIT_LOG " +
            "    (ENTITY_ID, ENTITY_TYPE, ACTION, ACTION_TIMESTAMP) " +
            "VALUES (?, 'CUSTOMER_REPORT', 'INSERT', CURRENT_TIMESTAMP)";

    private final JdbcTemplate reportJdbc;

    @Autowired
    public CustomerItemWriter(
            @Qualifier("reportDataSource") DataSource reportDataSource) {
        this.reportJdbc = new JdbcTemplate(reportDataSource);
    }

    @Override
    @Transactional
    public void write(Chunk<? extends ReportRecord> chunk) {
        List<? extends ReportRecord> items = chunk.getItems();
        log.debug("Writing {} report records", items.size());

        for (ReportRecord record : items) {
            reportJdbc.update(INSERT_REPORT_SQL,
                    record.getCustId(),
                    record.getFullName(),
                    record.getSegment(),
                    record.getTotalBalance(),
                    record.getAccountCount(),
                    record.getStatus(),
                    record.getReportDate());

            reportJdbc.update(INSERT_AUDIT_SQL, record.getCustId());
        }

        log.info("Wrote {} records to RPTSCHEMA.REPORT_TABLE", items.size());
    }
}
