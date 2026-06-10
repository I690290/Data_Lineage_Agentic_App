package com.example.lineage;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * TransactionProcessor — reads VALID.TRANS.OUTPUT file (produced by COBOL PROG002)
 * and writes to TRANSACTION_DETAIL table in the database.
 *
 * Data flow: TRANSACTION.INPUT.FILE → PROG002 → valid_trans.dat → TransactionProcessor → TRANSACTION_DETAIL
 */
@Service
public class TransactionProcessor {

    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final int BATCH_SIZE = 500;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    /**
     * Process the VALID-TRANS-OUTPUT file and load into TRANSACTION_DETAIL.
     * Reads the flat file written by COBOL PROG002 (VALIDOUT DD).
     *
     * @param validTransFilePath path to valid_trans.dat file
     * @return count of records inserted
     */
    @Transactional
    public int processValidTransactions(String validTransFilePath) throws IOException {
        List<TransactionRecord> batch = new ArrayList<>();
        int totalInserted = 0;

        try (BufferedReader reader = new BufferedReader(new FileReader(validTransFilePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                TransactionRecord record = parseTransactionLine(line);
                batch.add(record);

                if (batch.size() >= BATCH_SIZE) {
                    totalInserted += insertBatch(batch);
                    batch.clear();
                }
            }
            if (!batch.isEmpty()) {
                totalInserted += insertBatch(batch);
            }
        }

        return totalInserted;
    }

    /**
     * Parse a fixed-width record from valid_trans.dat (COBOL PROG002 output).
     * Field positions match VALID-TRANS-RECORD layout in PROG002.cbl.
     */
    private TransactionRecord parseTransactionLine(String line) {
        TransactionRecord r = new TransactionRecord();
        r.transactionId    = line.substring(0, 12).trim();
        r.accountNumber    = Long.parseLong(line.substring(12, 22).trim());
        r.transDate        = LocalDate.parse(line.substring(22, 30).trim(), DATE_FMT);
        r.transTime        = line.substring(30, 36).trim();
        r.transType        = line.substring(36, 40).trim();
        r.amount           = new BigDecimal(line.substring(40, 55).trim());
        r.currencyCode     = line.substring(55, 58).trim();
        r.merchantId       = line.substring(58, 78).trim();
        r.merchantCategory = line.substring(78, 82).trim();
        r.authCode         = line.substring(82, 88).trim();
        r.status           = line.substring(88, 90).trim();
        r.riskScore        = new BigDecimal(line.substring(90, 96).trim());
        r.loadedAt         = LocalDateTime.now();
        return r;
    }

    private int insertBatch(List<TransactionRecord> records) {
        String sql = """
                INSERT INTO TRANSACTION_DETAIL
                    (TRANSACTION_ID, ACCOUNT_NUMBER, TRANS_DATE, TRANS_TIME,
                     TRANS_TYPE, AMOUNT, CURRENCY_CODE, MERCHANT_ID,
                     MERCHANT_CATEGORY, AUTH_CODE, STATUS, RISK_SCORE, LOADED_AT)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (TRANSACTION_ID) DO UPDATE SET
                    STATUS = EXCLUDED.STATUS,
                    RISK_SCORE = EXCLUDED.RISK_SCORE,
                    LOADED_AT = EXCLUDED.LOADED_AT
                """;
        int[][] batchCounts = jdbcTemplate.batchUpdate(sql,
            records,
            records.size(),
            (ps, r) -> {
                ps.setString(1,  r.transactionId);
                ps.setLong(2,    r.accountNumber);
                ps.setDate(3,    java.sql.Date.valueOf(r.transDate));
                ps.setString(4,  r.transTime);
                ps.setString(5,  r.transType);
                ps.setBigDecimal(6, r.amount);
                ps.setString(7,  r.currencyCode);
                ps.setString(8,  r.merchantId);
                ps.setString(9,  r.merchantCategory);
                ps.setString(10, r.authCode);
                ps.setString(11, r.status);
                ps.setBigDecimal(12, r.riskScore);
                ps.setTimestamp(13, java.sql.Timestamp.valueOf(r.loadedAt));
            }
        );
        int total = 0;
        for (int[] row : batchCounts) {
            for (int c : row) total += c;
        }
        return total;
    }

    // ------- inner DTO -------

    private static class TransactionRecord {
        String transactionId;
        long accountNumber;
        LocalDate transDate;
        String transTime;
        String transType;
        BigDecimal amount;
        String currencyCode;
        String merchantId;
        String merchantCategory;
        String authCode;
        String status;
        BigDecimal riskScore;
        LocalDateTime loadedAt;
    }
}
