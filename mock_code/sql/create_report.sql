-- create_report.sql
-- Creates MONTHLY_REPORT view joining ACCOUNT_SUMMARY and TRANSACTION_DETAIL
-- This view is consumed by Java AccountService via JDBC

CREATE OR REPLACE VIEW MONTHLY_REPORT AS
WITH monthly_totals AS (
    SELECT
        td.ACCOUNT_NUMBER,
        EXTRACT(YEAR  FROM td.TRANS_DATE)  AS REPORT_YEAR,
        EXTRACT(MONTH FROM td.TRANS_DATE)  AS REPORT_MONTH,
        COUNT(*)                           AS TRANSACTION_COUNT,
        SUM(CASE WHEN td.TRANS_TYPE = 'PURCH' THEN td.AMOUNT ELSE 0 END)
                                           AS TOTAL_PURCHASES,
        SUM(CASE WHEN td.TRANS_TYPE = 'REFD'  THEN td.AMOUNT ELSE 0 END)
                                           AS TOTAL_REFUNDS,
        SUM(CASE WHEN td.TRANS_TYPE = 'WDRL'  THEN td.AMOUNT ELSE 0 END)
                                           AS TOTAL_WITHDRAWALS,
        SUM(CASE WHEN td.TRANS_TYPE = 'DEPO'  THEN td.AMOUNT ELSE 0 END)
                                           AS TOTAL_DEPOSITS,
        AVG(td.RISK_SCORE)                 AS AVG_RISK_SCORE,
        MAX(td.RISK_SCORE)                 AS MAX_RISK_SCORE
    FROM TRANSACTION_DETAIL td
    WHERE td.STATUS = 'VA'
    GROUP BY td.ACCOUNT_NUMBER,
             EXTRACT(YEAR  FROM td.TRANS_DATE),
             EXTRACT(MONTH FROM td.TRANS_DATE)
)
SELECT
    a.ACCOUNT_NUMBER,
    a.CUSTOMER_NAME,
    a.ACCOUNT_TYPE,
    a.BRANCH_CODE,
    a.PRODUCT_CODE,
    a.BALANCE              AS CURRENT_BALANCE,
    a.CREDIT_LIMIT,
    a.STATUS_CODE          AS ACCOUNT_STATUS,
    mt.REPORT_YEAR,
    mt.REPORT_MONTH,
    mt.TRANSACTION_COUNT,
    mt.TOTAL_PURCHASES,
    mt.TOTAL_REFUNDS,
    mt.TOTAL_WITHDRAWALS,
    mt.TOTAL_DEPOSITS,
    (mt.TOTAL_PURCHASES - mt.TOTAL_REFUNDS) AS NET_SPEND,
    mt.AVG_RISK_SCORE,
    mt.MAX_RISK_SCORE
FROM ACCOUNT_SUMMARY a
JOIN monthly_totals mt ON a.ACCOUNT_NUMBER = mt.ACCOUNT_NUMBER
WHERE a.STATUS_CODE IN ('AC', 'SU');
