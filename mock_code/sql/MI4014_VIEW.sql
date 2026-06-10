-- ================================================================
-- SCRIPT  : MI4014_VIEW.sql
-- SYSTEM  : Credit Risk Behaviour Scoring - Neptune Reporting
-- PURPOSE : Analytical views on MI4014 staging data for credit
--           risk behavioural scoring engine consumption.
-- ================================================================

-- ----------------------------------------------------------------
-- View 1: Clean validated transactions for scoring engine
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW "BDD_NEPTUNE_DICC"."V_MI4014_TRANSACCIONES_VALIDAS"
AS
SELECT
    MAIN_ACCOUNT_NUMBER,
    SUB_ACCOUNT_NUMBER,
    COMPANY,
    TRANSACTION_CODE,
    TRANSACTION_AMOUNT,
    TRANSACTION_GROUP,
    POSTED_DATE,
    EFFECTIVE_DATE,
    UNSECURED,
    NEW_MAIN_ACC_NUM,
    NEW_LOAN_ACC_NUM,
    LOAD_DATE,
    SOURCE_FILE
FROM "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
WHERE LOAD_STATUS = 'P'
  AND TRANSACTION_AMOUNT IS NOT NULL
  AND POSTED_DATE >= ADD_MONTHS(TRUNC(SYSDATE), -12);

-- ----------------------------------------------------------------
-- View 2: Account-level transaction summary for scoring features
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW "BDD_NEPTUNE_DICC"."V_MI4014_ACCOUNT_SUMMARY"
AS
SELECT
    MAIN_ACCOUNT_NUMBER,
    SUB_ACCOUNT_NUMBER,
    COMPANY,
    UNSECURED,
    COUNT(*)                                            AS TOTAL_TRANSACTIONS,
    SUM(TRANSACTION_AMOUNT)                             AS TOTAL_AMOUNT,
    SUM(CASE WHEN TRANSACTION_AMOUNT > 0
             THEN TRANSACTION_AMOUNT ELSE 0 END)        AS TOTAL_CREDITS,
    SUM(CASE WHEN TRANSACTION_AMOUNT < 0
             THEN ABS(TRANSACTION_AMOUNT) ELSE 0 END)   AS TOTAL_DEBITS,
    MIN(POSTED_DATE)                                    AS FIRST_TXN_DATE,
    MAX(POSTED_DATE)                                    AS LAST_TXN_DATE,
    COUNT(DISTINCT TRANSACTION_GROUP)                   AS DISTINCT_TXN_GROUPS,
    COUNT(DISTINCT TRANSACTION_CODE)                    AS DISTINCT_TXN_CODES,
    MAX(LOAD_DATE)                                      AS LAST_LOAD_DATE
FROM "BDD_NEPTUNE_DICC"."V_MI4014_TRANSACCIONES_VALIDAS"
GROUP BY
    MAIN_ACCOUNT_NUMBER,
    SUB_ACCOUNT_NUMBER,
    COMPANY,
    UNSECURED;

-- ----------------------------------------------------------------
-- View 3: Daily transaction load reconciliation view
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW "BDD_NEPTUNE_DICC"."V_MI4014_LOAD_AUDIT"
AS
SELECT
    TRUNC(LOAD_DATE)                                    AS LOAD_DATE,
    SOURCE_FILE,
    COUNT(*)                                            AS TOTAL_ROWS,
    SUM(CASE WHEN LOAD_STATUS = 'P' THEN 1 ELSE 0 END) AS PASSED_ROWS,
    SUM(CASE WHEN LOAD_STATUS = 'E' THEN 1 ELSE 0 END) AS ERROR_ROWS,
    SUM(CASE WHEN LOAD_STATUS = 'V' THEN 1 ELSE 0 END) AS VALIDATED_ROWS,
    COUNT(DISTINCT MAIN_ACCOUNT_NUMBER)                 AS DISTINCT_ACCOUNTS,
    SUM(TRANSACTION_AMOUNT)                             AS TOTAL_AMOUNT,
    MIN(POSTED_DATE)                                    AS MIN_POSTED_DATE,
    MAX(POSTED_DATE)                                    AS MAX_POSTED_DATE
FROM "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
GROUP BY TRUNC(LOAD_DATE), SOURCE_FILE
ORDER BY TRUNC(LOAD_DATE) DESC;
