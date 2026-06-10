package com.example.batch;

import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;

/**
 * Reads active customer records from CUSTSCHEMA.CUSTOMER_TABLE.
 * Uses the primary customerDataSource (CUSTDB).
 */
@Component
public class CustomerItemReader extends JdbcCursorItemReader<CustomerRecord> {

    private static final String CUSTOMER_SELECT_SQL =
            "SELECT " +
            "    CUST_ID, " +
            "    CUST_FIRST_NAME, " +
            "    CUST_LAST_NAME, " +
            "    CUST_EMAIL, " +
            "    CUST_PHONE, " +
            "    CUST_SEGMENT, " +
            "    CUST_SINCE_DATE, " +
            "    CUST_STATUS " +
            "FROM CUSTSCHEMA.CUSTOMER_TABLE " +
            "WHERE CUST_STATUS = 'A' " +
            "ORDER BY CUST_ID";

    @Autowired
    public CustomerItemReader(
            @Qualifier("customerDataSource") DataSource customerDataSource,
            @Value("${batch.chunk-size:1000}") int fetchSize) {

        setName("customerItemReader");
        setDataSource(customerDataSource);
        setSql(CUSTOMER_SELECT_SQL);
        setRowMapper(new BeanPropertyRowMapper<>(CustomerRecord.class));
        setFetchSize(fetchSize);
        setSaveState(true);
    }
}
