      *================================================================
      * PROGRAM  : CRTXNEXT
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * MODULE   : MI4014 Daily Transaction Extract - Phase 2
      * PURPOSE  : Extract daily transactions from DB2 for each
      *            account in the customer extract file.
      *            Uses CUST.BHSCORE.EXTRACT as driving file,
      *            queries CRISK.DAILY_TRANSACTIONS per account.
      *
      * INPUT    : BHSCOEXT - CUST.BHSCORE.EXTRACT (FB/LRECL=140)
      *                       produced by CRDB2EXT
      * OUTPUT   : BHSCOTXN - TRANS.BHSCORE.EXTRACT (FB/LRECL=160)
      *
      * CALLED BY: JCL CRJBHSCR STEP020
      * CALLS    : None
      *
      * DB2 TABLES ACCESSED:
      *   READ   : CRISK.DAILY_TRANSACTIONS (cursor per account)
      *
      * RETURN CODES:
      *   0000 = Successful completion
      *   0008 = DB2 error encountered
      *   0012 = File I/O error
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRTXNEXT.
       AUTHOR. CREDIT-RISK-BATCH.
       DATE-WRITTEN. 2024-03-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUST-EXTRACT-FILE
               ASSIGN TO BHSCOEXT
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-CUST-STATUS.

           SELECT TRANS-EXTRACT-FILE
               ASSIGN TO BHSCOTXN
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-TRANS-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  CUST-EXTRACT-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 140 CHARACTERS.
       COPY CRCUSTAC.

       FD  TRANS-EXTRACT-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 160 CHARACTERS.
       COPY CRTRANSR.

       WORKING-STORAGE SECTION.
      *----------------------------------------------------------------
      * File statuses
      *----------------------------------------------------------------
       01  WS-FILE-STATUS.
           05  WS-CUST-STATUS      PIC XX   VALUE SPACES.
           05  WS-TRANS-STATUS     PIC XX   VALUE SPACES.

       01  WS-COUNTERS.
           05  WS-ACCTS-READ       PIC 9(9) VALUE ZEROS.
           05  WS-TRANS-FETCHED    PIC 9(9) VALUE ZEROS.
           05  WS-TRANS-WRITTEN    PIC 9(9) VALUE ZEROS.
           05  WS-ACCTS-NO-TXN     PIC 9(9) VALUE ZEROS.

       01  WS-FLAGS.
           05  WS-CUST-EOF         PIC X    VALUE 'N'.
               88  CUST-EOF-REACHED VALUE 'Y'.
           05  WS-TXN-EOF          PIC X    VALUE 'N'.
               88  TXN-EOF-REACHED  VALUE 'Y'.

       01  WS-RETURN-CODE          PIC S9(4) COMP VALUE ZEROS.
       01  WS-SQLCODE-SAVE         PIC S9(9) COMP VALUE ZEROS.
       01  WS-PROCESS-DATE         PIC X(8).

      *----------------------------------------------------------------
      * DB2 host variables for DAILY_TRANSACTIONS cursor
      *----------------------------------------------------------------
       01  HV-TXN-QUERY-PARAMS.
           05  HV-QUERY-EXT-ACCT   PIC X(20).
           05  HV-QUERY-SUB-ACCT   PIC X(10).

       01  HV-TRANSACTION.
           05  HV-TXN-EXT-ACCT     PIC X(20).
           05  HV-TXN-SUB-ACCT     PIC X(10).
           05  HV-TXN-BOOK-ID      PIC X(6).
           05  HV-TXN-CODE         PIC X(10).
           05  HV-TXN-AMT          PIC S9(13)V99 COMP-3.
           05  HV-TXN-AMT-DISP     PIC -9(13).99.
           05  HV-TXN-CATEGORY     PIC X(6).
           05  HV-TXN-POSTED-DT    PIC X(10).
           05  HV-TXN-EFFECTIVE-DT PIC X(10).
           05  HV-TXN-UNSECURED    PIC X(1).
           05  HV-TXN-NEW-MAIN     PIC X(20).
           05  HV-TXN-NEW-LOAN     PIC X(20).

      *----------------------------------------------------------------
      * Work record to hold current customer extract row
      *----------------------------------------------------------------
       01  WS-CUST-WORK-REC.
           05  WS-CUST-EXT-ACCT    PIC X(20).
           05  WS-CUST-SUB-ACCT    PIC X(10).
           05  WS-CUST-BOOK-ID     PIC X(6).
           05  WS-CUST-UNSECURED   PIC X(1).
           05  WS-CUST-NEW-MAIN    PIC X(20).
           05  WS-CUST-NEW-LOAN    PIC X(20).
           05  FILLER              PIC X(83).

      *----------------------------------------------------------------
      * SQLCA - DB2 communication area
      *----------------------------------------------------------------
           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM READ-CUST-LOOP-PARA UNTIL CUST-EOF-REACHED.
           PERFORM CLOSE-FILES-PARA.
           PERFORM DISPLAY-TOTALS-PARA.
           MOVE WS-RETURN-CODE TO RETURN-CODE.
           STOP RUN.

      *================================================================
       INIT-PARA.
           MOVE ZEROS TO WS-COUNTERS.
           MOVE 'N' TO WS-CUST-EOF.
           MOVE FUNCTION CURRENT-DATE(1:8) TO WS-PROCESS-DATE.

           OPEN INPUT  CUST-EXTRACT-FILE.
           IF WS-CUST-STATUS NOT = '00'
               DISPLAY 'CRTXNEXT: OPEN ERROR BHSCOEXT STATUS='
                       WS-CUST-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           OPEN OUTPUT TRANS-EXTRACT-FILE.
           IF WS-TRANS-STATUS NOT = '00'
               DISPLAY 'CRTXNEXT: OPEN ERROR BHSCOTXN STATUS='
                       WS-TRANS-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.

           DISPLAY 'CRTXNEXT: INIT COMPLETE. PROCESS-DATE=' WS-PROCESS-DATE.

      *================================================================
       READ-CUST-LOOP-PARA.
      *    Read one customer account from input file
           READ CUST-EXTRACT-FILE INTO WS-CUST-WORK-REC
               AT END MOVE 'Y' TO WS-CUST-EOF
           END-READ.

           IF CUST-EOF-REACHED
               NEXT SENTENCE
           ELSE
               ADD 1 TO WS-ACCTS-READ
               MOVE WS-CUST-EXT-ACCT TO HV-QUERY-EXT-ACCT
               MOVE WS-CUST-SUB-ACCT TO HV-QUERY-SUB-ACCT
               PERFORM FETCH-TRANSACTIONS-PARA
           END-IF.

      *================================================================
       FETCH-TRANSACTIONS-PARA.
      *    Open cursor for this account's daily transactions
      *    DB2 DAILY_TRANSACTIONS joined back to account fields
           EXEC SQL
               DECLARE CSR_DAILY_TXN CURSOR FOR
               SELECT
                   TRIM(T.EXTERNAL_ACCOUNT_NUMBER),
                   TRIM(T.SUB_ACCOUNT_NUMBER),
                   TRIM(T.BOOK_ID),
                   TRIM(T.TRANSACTION_CODE),
                   T.TRANSACTION_AMT,
                   CHAR(T.TRANSACTION_AMT),
                   TRIM(T.TRAN_CATEGORY),
                   VARCHAR_FORMAT(T.POSTED_DATE, 'YYYY-MM-DD'),
                   VARCHAR_FORMAT(T.EFFECTIVE_DATE, 'YYYY-MM-DD'),
                   TRIM(T.UNSECURED_IND),
                   COALESCE(TRIM(T.NEW_MAIN_ACCOUNT_NUMBER), ' '),
                   COALESCE(TRIM(T.NEW_LOAN_ACCOUNT_NUMBER), ' ')
               FROM CRISK.DAILY_TRANSACTIONS T
               WHERE T.EXTERNAL_ACCOUNT_NUMBER = :HV-QUERY-EXT-ACCT
                 AND T.SUB_ACCOUNT_NUMBER      = :HV-QUERY-SUB-ACCT
                 AND T.PROCESS_DATE            = CURRENT DATE
               ORDER BY T.POSTED_DATE DESC,
                        T.TRANSACTION_CODE
           END-EXEC.

           EXEC SQL
               OPEN CSR_DAILY_TXN
           END-EXEC.

           IF SQLCODE NOT = 0
               DISPLAY 'CRTXNEXT: OPEN CURSOR FAIL ACCT='
                       HV-QUERY-EXT-ACCT ' SQLCODE=' SQLCODE
               MOVE 8 TO WS-RETURN-CODE
               GO TO END-FETCH-TRANSACTIONS
           END-IF.

           MOVE 'N' TO WS-TXN-EOF.
           PERFORM FETCH-TXN-LOOP-PARA UNTIL TXN-EOF-REACHED.

           IF WS-TRANS-FETCHED = 0
               ADD 1 TO WS-ACCTS-NO-TXN
           END-IF.

           EXEC SQL
               CLOSE CSR_DAILY_TXN
           END-EXEC.

       END-FETCH-TRANSACTIONS.
           CONTINUE.

      *================================================================
       FETCH-TXN-LOOP-PARA.
           EXEC SQL
               FETCH CSR_DAILY_TXN
               INTO  :HV-TXN-EXT-ACCT,
                     :HV-TXN-SUB-ACCT,
                     :HV-TXN-BOOK-ID,
                     :HV-TXN-CODE,
                     :HV-TXN-AMT,
                     :HV-TXN-AMT-DISP,
                     :HV-TXN-CATEGORY,
                     :HV-TXN-POSTED-DT,
                     :HV-TXN-EFFECTIVE-DT,
                     :HV-TXN-UNSECURED,
                     :HV-TXN-NEW-MAIN,
                     :HV-TXN-NEW-LOAN
           END-EXEC.

           EVALUATE SQLCODE
               WHEN 0
                   ADD 1 TO WS-TRANS-FETCHED
                   PERFORM WRITE-TRANSACTION-PARA
               WHEN 100
                   MOVE 'Y' TO WS-TXN-EOF
               WHEN OTHER
                   MOVE SQLCODE TO WS-SQLCODE-SAVE
                   DISPLAY 'CRTXNEXT: FETCH TXN ERROR SQLCODE='
                           WS-SQLCODE-SAVE
                   MOVE 8 TO WS-RETURN-CODE
                   MOVE 'Y' TO WS-TXN-EOF
           END-EVALUATE.

      *================================================================
       WRITE-TRANSACTION-PARA.
      *    Merge customer account fields with transaction data
      *    Account master fields come from driving file (input)
      *    Transaction fields come from DB2 cursor fetch
           MOVE HV-TXN-EXT-ACCT    TO CTR-EXTERNAL-ACCT-NUM.
           MOVE HV-TXN-SUB-ACCT    TO CTR-SUB-ACCOUNT-NUM.
           MOVE HV-TXN-BOOK-ID     TO CTR-BOOK-ID.
           MOVE HV-TXN-CODE        TO CTR-TRANSACTION-CODE.
           MOVE HV-TXN-AMT         TO CTR-TRANSACTION-AMT.
           MOVE HV-TXN-AMT-DISP    TO CTR-TRAN-AMT-DISPLAY.
           MOVE HV-TXN-CATEGORY    TO CTR-TRAN-CATEGORY.
           MOVE HV-TXN-POSTED-DT   TO CTR-POSTED-DATE.
           MOVE HV-TXN-EFFECTIVE-DT TO CTR-EFFECTIVE-DATE.
           MOVE HV-TXN-UNSECURED   TO CTR-UNSECURED-IND.
      *    New account numbers: prefer transaction value, fall back to
      *    customer master (populated during account consolidation)
           IF HV-TXN-NEW-MAIN NOT = SPACES
               MOVE HV-TXN-NEW-MAIN TO CTR-NEW-MAIN-ACCT-NUM
           ELSE
               MOVE WS-CUST-NEW-MAIN TO CTR-NEW-MAIN-ACCT-NUM
           END-IF.
           IF HV-TXN-NEW-LOAN NOT = SPACES
               MOVE HV-TXN-NEW-LOAN TO CTR-NEW-LOAN-ACCT-NUM
           ELSE
               MOVE WS-CUST-NEW-LOAN TO CTR-NEW-LOAN-ACCT-NUM
           END-IF.

           WRITE CR-TRANSACTION-REC.
           IF WS-TRANS-STATUS NOT = '00'
               DISPLAY 'CRTXNEXT: WRITE ERROR STATUS=' WS-TRANS-STATUS
               MOVE 12 TO WS-RETURN-CODE
               STOP RUN
           END-IF.
           ADD 1 TO WS-TRANS-WRITTEN.

      *================================================================
       CLOSE-FILES-PARA.
           CLOSE CUST-EXTRACT-FILE.
           CLOSE TRANS-EXTRACT-FILE.

      *================================================================
       DISPLAY-TOTALS-PARA.
           DISPLAY '**CRTXNEXT TOTALS**'.
           DISPLAY '  INPUT  DATASET  : CUST.BHSCORE.EXTRACT'.
           DISPLAY '  DB2 TABLE READ  : CRISK.DAILY_TRANSACTIONS'.
           DISPLAY '  OUTPUT DATASET  : TRANS.BHSCORE.EXTRACT'.
           DISPLAY '  ACCOUNTS READ   : ' WS-ACCTS-READ.
           DISPLAY '  TRANS FETCHED   : ' WS-TRANS-FETCHED.
           DISPLAY '  TRANS WRITTEN   : ' WS-TRANS-WRITTEN.
           DISPLAY '  ACCTS NO TRANS  : ' WS-ACCTS-NO-TXN.
           DISPLAY '  RETURN CODE     : ' WS-RETURN-CODE.
