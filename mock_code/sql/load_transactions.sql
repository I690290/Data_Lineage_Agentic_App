-- load_transactions.sql
-- Loads TRANSACTION_DETAIL from the COBOL PROG002 output file (valid_trans.dat)
-- Source: VALID.TRANS.OUTPUT (DD: VALIDOUT from JCL STEP020)

LOAD DATA
    INFILE 'valid_trans.dat'
    INTO TABLE TRANSACTION_DETAIL
    FIELDS TERMINATED BY '|'
    LINES TERMINATED BY '\n'
    (
        TRANSACTION_ID    POSITION(1:12)    CHAR,
        ACCOUNT_NUMBER    POSITION(13:22)   INTEGER EXTERNAL,
        TRANS_DATE        POSITION(23:30)   DATE FORMAT 'YYYYMMDD',
        TRANS_TIME        POSITION(31:36)   CHAR,
        TRANS_TYPE        POSITION(37:40)   CHAR,
        AMOUNT            POSITION(41:55)   DECIMAL EXTERNAL,
        CURRENCY_CODE     POSITION(56:58)   CHAR,
        MERCHANT_ID       POSITION(59:78)   CHAR,
        MERCHANT_CATEGORY POSITION(79:82)   CHAR,
        AUTH_CODE         POSITION(83:88)   CHAR,
        STATUS            POSITION(89:90)   CHAR,
        RISK_SCORE        POSITION(91:96)   DECIMAL EXTERNAL
    )
    LOG FILE 'load_transactions.log'
    BAD FILE 'load_transactions.bad'
    DISCARD FILE 'load_transactions.dsc'
    DISCARD MAX 100;
